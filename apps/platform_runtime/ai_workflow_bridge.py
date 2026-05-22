"""
AI → workflow bridge (structured suggestions only; **no** auto-actions, **no** silent writes).

Emits machine-readable suggestion objects that UIs or schedulers can display; humans or
existing approval flows must execute any real change.
"""

from __future__ import annotations

from typing import Any


def build_structured_workflow_suggestions(
    *,
    school,
    user,
    health_snapshot: dict[str, Any] | None = None,
    onboarding_keys: list[str] | None = None,
    analytics_keys: list[str] | None = None,
) -> dict[str, Any]:
    """
    Rule-based, tenant-scoped suggestions. Optional LLM copy can be merged by callers
    (e.g. suggest_next_actions) but is not required for a valid payload.
    """
    _ = user
    sid = str(getattr(school, "pk", "") or "")
    suggestions: list[dict[str, Any]] = []
    h = health_snapshot if isinstance(health_snapshot, dict) else {}
    risk = str(h.get("risk_tier") or h.get("tier") or "").lower()
    if risk in ("high", "at_risk", "critical"):
        suggestions.append(
            {
                "id": "health_risk_review",
                "kind": "health",
                "title": "Review at-risk signals in the school health dashboard",
                "safe_href": "/authentication/backend/",
                "risk_tier": "low",
                "machine": {"trigger": "health_snapshot", "school_id": sid},
            }
        )
    onb = onboarding_keys or []
    if onb:
        suggestions.append(
            {
                "id": "onboarding_continue",
                "kind": "onboarding",
                "title": "Continue guided onboarding for open configuration steps",
                "safe_href": "/siteconfig/guided-onboarding/",
                "risk_tier": "low",
                "machine": {"open_keys": onb[:20], "school_id": sid},
            }
        )
    an = analytics_keys or []
    if an:
        suggestions.append(
            {
                "id": "analytics_digest",
                "kind": "analytics",
                "title": "Open analytics or scheduled reports for the active term",
                "safe_href": "/siteconfig/reports/scheduled/",
                "risk_tier": "low",
                "machine": {"metric_keys": an[:20], "school_id": sid},
            }
        )
    return {
        "schema_version": 1,
        "school_id": sid,
        "suggestions": suggestions,
        "requires_human_approval": True,
    }


def bind_workflow_context_for_ai(
    *,
    request: Any,
    workflow_key: str | None = None,
) -> dict[str, Any]:
    """Build a structured AI-context dict for a request + workflow.

    Phase 4 Wave E AI-bridge wiring. Returns the input the AI gateway should
    consume when answering "what should I do next on this workflow?" — but
    NEVER calls the gateway itself. Routing remains the caller's
    responsibility via ``services.ai_helpers.invoke_with_request`` (canonical
    boundary; direct ``services.ai_gateway`` imports outside the 5-file
    allowlist are forbidden by ``scan_ai_gateway_boundary.py``).

    Resolution policy:
      * If ``workflow_key`` is supplied, look it up directly via
        ``workflow_guidance.get_workflow``.
      * Otherwise, ``workflow_guidance.resolve_workflow_for_route(request)``
        matches by URL view-name or ``entry_path`` prefix.
      * If neither resolves OR the workflow fails the 3-layer visibility
        gate, return the DATA DEFAULTER shape: ``{workflow_key: None,
        next_action: None, evidence_id: None}`` so the AI can still respond
        without fabricating.

    Tenant-safety:
      * ``platform-only`` tag chips and audit IDs are stripped on tenant
        hosts by ``tags_for`` before reaching this function's caller.
      * The bridge NEVER emits raw tenant IDs to the AI; we use the
        hashed-tenant pattern from v3.38.0 metrics (``_hash_tenant_id``).

    Output shape (stable; the AI gateway dispatch table reads on it):
        {
            "schema_version": 1,
            "workflow_key": str | None,
            "workflow_title": str,
            "audience": str,                # operator | tenant-admin | teacher | ...
            "module": str,                  # owning app slug
            "route": str,                   # URL name OR path (entry_path)
            "ai_context_key": str | None,   # workflow.related_ai_context_key
            "tags": list[dict],             # filtered through visibility gate
            "host_kind": str,               # tenant | manager | marketing | docs | api
            "data_defaulter": bool,         # True when no workflow resolved
        }
    """
    # Lazy-import inside the function so this module stays a leaf in the
    # dependency graph (workflow_guidance imports workflow_registry only).
    from apps.platform_runtime.workflow_guidance import (  # noqa: WPS433
        _host_kind,
        get_workflow,
        is_visible_for,
        resolve_workflow_for_route,
        tags_for,
    )

    workflow = None
    if workflow_key:
        workflow = get_workflow(workflow_key)
    if workflow is None:
        workflow = resolve_workflow_for_route(request)

    host_kind = _host_kind(request)

    # DATA DEFAULTER posture — never fabricate when context is absent.
    if workflow is None or not is_visible_for(request, workflow):
        return {
            "schema_version": 1,
            "workflow_key": None,
            "workflow_title": "",
            "audience": "",
            "module": "",
            "route": "",
            "ai_context_key": None,
            "tags": [],
            "host_kind": host_kind,
            "data_defaulter": True,
        }

    return {
        "schema_version": 1,
        "workflow_key": workflow.key,
        "workflow_title": workflow.title,
        "audience": workflow.audience,
        "module": workflow.module,
        "route": workflow.route or (getattr(workflow, "entry_path", None) or ""),
        "ai_context_key": getattr(workflow, "related_ai_context_key", None),
        "tags": tags_for(request, workflow),
        "host_kind": host_kind,
        "data_defaulter": False,
    }


def build_ai_approval_handoff(
    *,
    recommendation: dict[str, Any],
    approved: bool,
    approver_user_id: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """
    Deterministic handoff payload from AI suggestion to operator action.
    This function does not execute side effects; callers use the payload to route work.
    """
    rec_key = str((recommendation or {}).get("recommendation_key") or "").strip()[:120]
    proposal = str((recommendation or {}).get("proposed_action") or "").strip()[:2000]
    status = "approved_for_execution" if approved else "rejected"
    return {
        "schema_version": 1,
        "recommendation_key": rec_key or "unknown",
        "status": status,
        "requires_human_approval": True,
        "approved_by_user_id": int(approver_user_id) if approver_user_id else None,
        "operator_notes": (notes or "").strip()[:1000],
        "proposed_action": proposal,
    }
