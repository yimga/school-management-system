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
