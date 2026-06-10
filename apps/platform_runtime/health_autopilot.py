"""
Health self-healing engine — Phase 1 (autonomous tenant remediation, SHADOW by default).

This extends the proven Workflow Autopilot pattern (curated reversible auto-fix kinds,
per-tenant policy gate, apply log) from *workflow failures* to *tenant health signals*.

SAFETY CONTRACT — do not relax any clause without review (locked by
``scripts/verify_health_autopilot_safety.py``):

  1. SHADOW BY DEFAULT. ``try_auto_apply`` proposes and previews but applies NOTHING
     unless a ``WorkflowAutopilotPolicy`` row (workflow_key="health_autopilot") explicitly
     enables the proposed kind for the tenant scope. No policy => no mutation. The operator
     creating that policy row is the human authorization.

  2. CURATED, REVERSIBLE/IDEMPOTENT KINDS ONLY. Every entry in ``HEALTH_REMEDIATION_KINDS``
     reuses an existing, vetted, idempotent platform operation. No data deletion, no money
     mutation, no source-file writes. ``reversible=True`` is an invariant.

  3. THE INBUILT AI WIDENS MATCHING, IT NEVER INVENTS ACTIONS. For an unknown signal the
     AI may only *classify* it onto an EXISTING kind key at/above ``AI_MIN_CONFIDENCE``;
     any kind the AI returns that is not already in the catalog is discarded. AI is disabled
     by default (RUNMYCAMPUS_AI_ENABLED) and routed through the RBAC-guarded
     ``apps.platform_runtime.ai_providers.run_ai_prompt`` facade.

  4. EVERY APPLY IS LOGGED — ``WorkflowAutopilotApplyLog`` (queryable, namespaced by
     workflow_key) + a structured log line carrying school slug + signal + source + outcome.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

WORKFLOW_KEY = "health_autopilot"

# The inbuilt AI may only *promote* an unknown signal to a curated kind at/above this floor.
AI_MIN_CONFIDENCE = 0.7

# --- Curated remediation kinds (reversible/idempotent; reuse vetted operations only) ---
KIND_REBUILD_OFFLINE_MANIFEST = "rebuild_offline_manifest"
KIND_RECOMPUTE_HEALTH_SNAPSHOT = "recompute_health_snapshot"

HEALTH_REMEDIATION_KINDS: dict[str, dict[str, Any]] = {
    KIND_REBUILD_OFFLINE_MANIFEST: {
        "label": "Rebuild offline manifest",
        "description": (
            "Re-resolve and re-apply the country-enriched offline-mode bundle for the "
            "tenant. Idempotent: refreshes the offline manifest flag without touching data."
        ),
        "scope": "school",
        "reversible": True,
    },
    KIND_RECOMPUTE_HEALTH_SNAPSHOT: {
        "label": "Recompute platform health snapshot",
        "description": (
            "Invalidate the cached platform-health summary and recompute it fresh so a "
            "transient/degraded reading clears. Cache-only; no tenant data is mutated."
        ),
        "scope": "platform",
        "reversible": True,
    },
}

# --- Deterministic signal -> kind rules (tried before any AI) ---
_SIGNAL_RULES: dict[str, str] = {
    "tenant_offline_unconfigured": KIND_REBUILD_OFFLINE_MANIFEST,
    "offline_manifest_stale": KIND_REBUILD_OFFLINE_MANIFEST,
    "platform_health_degraded": KIND_RECOMPUTE_HEALTH_SNAPSHOT,
    "feature_gap_broken_proof": KIND_RECOMPUTE_HEALTH_SNAPSHOT,
}


def _norm_signal(signal: Any) -> str:
    return str(signal or "").strip().lower()[:80]


def propose_remediation(signal, *, school=None, user=None) -> dict[str, Any]:
    """Map a health signal to a curated remediation kind.

    Deterministic rules first; for an unknown signal the inbuilt AI may classify it onto an
    EXISTING kind (never invent one). ``auto_fix_available`` is True only when the resolved
    kind is in the curated catalog.
    """
    sig = _norm_signal(signal)
    if not sig:
        return {
            "verdict": "no_match",
            "signal": sig,
            "kind": None,
            "auto_fix_available": False,
            "human_action": "Empty signal; nothing to remediate.",
        }

    kind = _SIGNAL_RULES.get(sig)
    source = "rule"
    confidence = 1.0
    if kind is None:
        ai = _classify_signal_with_ai(sig, school=school, user=user)
        if ai is not None:
            kind, confidence = ai
            source = "ai"

    if kind and kind in HEALTH_REMEDIATION_KINDS:
        meta = HEALTH_REMEDIATION_KINDS[kind]
        return {
            "verdict": "match",
            "signal": sig,
            "kind": kind,
            "source": source,
            "confidence": round(float(confidence), 3),
            "reversible": bool(meta["reversible"]),
            "scope": meta["scope"],
            "label": meta["label"],
            "description": meta["description"],
            "auto_fix_available": True,
        }

    return {
        "verdict": "no_match",
        "signal": sig,
        "kind": None,
        "source": source,
        "auto_fix_available": False,
        "human_action": "No safe automatic remediation matched; inspect the health detail.",
    }


def _classify_signal_with_ai(signal: str, *, school=None, user=None) -> tuple[str, float] | None:
    """Best-effort: ask the inbuilt AI to map an unknown signal onto an EXISTING kind.

    Returns ``(kind, confidence)`` only when the AI names a catalog kind at/above
    ``AI_MIN_CONFIDENCE``; otherwise ``None``. AI is disabled by default and this returns
    ``None`` without any model call when off. Never raises.
    """
    try:
        from apps.platform_runtime.ai_providers import get_ai_runtime_config, run_ai_prompt
    except Exception:  # noqa: BLE001
        return None

    try:
        if not get_ai_runtime_config(school=school).get("enabled"):
            return None
    except Exception:  # noqa: BLE001
        return None

    allowed = sorted(HEALTH_REMEDIATION_KINDS.keys())
    prompt = (
        "You are a remediation classifier. Map the health signal to EXACTLY ONE of the "
        'allowed remediation kinds, or "none" if no kind clearly applies. You may not '
        "invent a kind outside the list. Respond with JSON only: "
        '{"kind": "<one of the allowed kinds or none>", "confidence": <0..1>}.'
    )
    context = json.dumps({"signal": signal, "allowed_kinds": allowed})

    try:
        text, _meta = run_ai_prompt(
            prompt, context, school, user=user, prompt_type="health_autopilot_classify"
        )
    except Exception:  # noqa: BLE001
        logger.warning("health_autopilot_ai_classify_failed signal=%s", signal)
        return None

    parsed = _parse_ai_kind(text)
    if parsed is None:
        return None
    kind, conf = parsed
    if kind not in HEALTH_REMEDIATION_KINDS:
        # The AI proposed something outside the curated catalog — discard (never invent).
        return None
    if conf < AI_MIN_CONFIDENCE:
        return None
    return kind, conf


def _parse_ai_kind(text: Any) -> tuple[str, float] | None:
    raw = text if isinstance(text, str) else str(text or "")
    if not raw.strip():
        return None
    obj: Any = None
    try:
        obj = json.loads(raw)
    except Exception:  # noqa: BLE001
        match = re.search(r"\{[^{}]*\}", raw)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            return None
    if not isinstance(obj, dict):
        return None
    kind = str(obj.get("kind") or "").strip()
    if not kind or kind == "none":
        return None
    try:
        conf = float(obj.get("confidence"))
    except (TypeError, ValueError):
        return None
    conf = max(0.0, min(1.0, conf))
    return kind, conf


def preview_remediation(kind: str, *, school=None) -> dict[str, Any]:
    """Describe what apply WOULD do — no mutation (shadow)."""
    meta = HEALTH_REMEDIATION_KINDS.get(kind)
    if meta is None:
        return {"ok": False, "dry_run": True, "reason": "unsupported_kind", "kind": kind}
    return {
        "ok": True,
        "dry_run": True,
        "would_apply": kind,
        "scope": meta["scope"],
        "reversible": meta["reversible"],
        "note": meta["description"],
        "needs_school": meta["scope"] == "school",
    }


def _apply_kind(kind: str, *, school=None) -> dict[str, Any]:
    """Execute a curated remediation kind. Idempotent. Returns a JSON-serializable result."""
    if kind == KIND_REBUILD_OFFLINE_MANIFEST:
        if school is None:
            return {"ok": False, "reason": "missing_school", "kind": kind}
        try:
            from apps.platform_runtime.offline_mode_bundle import (
                apply_offline_mode_bundle_for_school,
            )

            result = apply_offline_mode_bundle_for_school(school, dry_run=False)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:80]}", "kind": kind}
        return {
            "ok": True,
            "applied": kind,
            "enable_offline_mode": result.get("enable_offline_mode"),
        }

    if kind == KIND_RECOMPUTE_HEALTH_SNAPSHOT:
        try:
            from apps.platform_runtime.platform_health import (
                bust_summary_cache,
                platform_health_summary,
            )

            bust_summary_cache()
            summary = platform_health_summary(use_cache=False)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:80]}", "kind": kind}
        return {
            "ok": True,
            "applied": kind,
            "level": summary.get("level"),
            "count": summary.get("count"),
        }

    return {"ok": False, "reason": "unsupported_kind", "kind": kind}


def _tenant_scope_for(school) -> str:
    if school is None:
        return ""
    return str(getattr(school, "schema_name", "") or getattr(school, "slug", "") or "")[:64]


def record_health_log(
    *,
    school=None,
    signal="",
    kind="",
    source="rule",
    confidence=0.0,
    mode="shadow",
    outcome="proposed",
    reversible=True,
    detail=None,
) -> None:
    """Write a school-attributed ``HealthRemediationLog`` row. Best-effort; never raises."""
    try:
        from apps.platform_runtime.models import HealthRemediationLog

        HealthRemediationLog.objects.create(
            school=school if (school is not None and getattr(school, "pk", None)) else None,
            school_slug=str(getattr(school, "slug", "") or "")[:80],
            signal=str(signal or "")[:80],
            kind=str(kind or "")[:64],
            source=str(source or "rule")[:16],
            confidence=float(confidence or 0.0),
            mode=str(mode or "shadow")[:16],
            outcome=str(outcome or "proposed")[:24],
            reversible=bool(reversible),
            detail=detail or {},
        )
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_remediation_log_failed", exc_info=True)


def try_auto_apply(
    *, signal, school=None, user=None, actor_user_id="", record_shadow=False
) -> dict[str, Any]:
    """Propose remediation and apply ONLY if a policy enables the kind (else shadow).

    Default (no policy) => ``mode="shadow"``, ``applied=False`` plus a preview. The engine
    never mutates tenant state until an operator opts the kind in via
    ``WorkflowAutopilotPolicy`` (workflow_key="health_autopilot"). ``record_shadow=True``
    persists the shadow proposal to ``HealthRemediationLog`` for operator review.
    """
    prop = propose_remediation(signal, school=school, user=user)
    if not prop.get("auto_fix_available"):
        if record_shadow:
            record_health_log(
                school=school, signal=prop["signal"], kind="", source=prop.get("source", "rule"),
                mode="shadow", outcome="skipped", detail={"verdict": prop.get("verdict")},
            )
        return {**prop, "mode": "shadow", "applied": False}

    kind = prop["kind"]
    scope = _tenant_scope_for(school)

    allowed = False
    try:
        from apps.platform_runtime.workflow_autopilot import policy_allows_auto_fix

        allowed = policy_allows_auto_fix(
            workflow_key=WORKFLOW_KEY, auto_fix_kind=kind, tenant_schema=scope
        )
    except Exception:  # noqa: BLE001
        allowed = False

    if not allowed:
        if record_shadow:
            record_health_log(
                school=school, signal=prop["signal"], kind=kind, source=prop.get("source", "rule"),
                confidence=prop.get("confidence", 0.0), reversible=prop.get("reversible", True),
                mode="shadow", outcome="proposed", detail={"reason": "policy_disabled"},
            )
        return {
            **prop,
            "mode": "shadow",
            "applied": False,
            "reason": "policy_disabled",
            "preview": preview_remediation(kind, school=school),
        }

    result = _apply_kind(kind, school=school)
    outcome = "applied" if result.get("ok") else "failed"

    try:
        from apps.platform_runtime.workflow_autopilot import record_apply_log

        record_apply_log(
            run_id=0,  # health applies are not bound to a WorkflowRun; namespaced by workflow_key
            workflow_key=WORKFLOW_KEY,
            auto_fix_kind=kind,
            outcome=outcome,
            actor_user_id=str(actor_user_id or ""),
            autopilot=True,
        )
    except Exception:  # noqa: BLE001
        logger.debug("health_autopilot_apply_log_failed", exc_info=True)

    record_health_log(
        school=school,
        signal=prop["signal"],
        kind=kind,
        source=prop.get("source", "rule"),
        confidence=prop.get("confidence", 0.0),
        reversible=prop.get("reversible", True),
        mode="apply",
        outcome=outcome,
        detail={"result": result},
    )

    school_slug = str(getattr(school, "slug", "") or "-")
    logger.info(
        "health_autopilot_apply school=%s signal=%s kind=%s source=%s outcome=%s",
        school_slug,
        prop["signal"],
        kind,
        prop.get("source"),
        outcome,
    )

    return {
        **prop,
        "mode": "apply",
        "applied": bool(result.get("ok")),
        "result": result,
        "tenant_scope": scope,
    }


# --- Conservative signal producers (real state -> well-defined signals) ---

def iter_school_signals(school) -> list[str]:
    """Conservative school-scope signals derived from real health state.

    Intentionally small: a ``setup_needed`` tenant may not have its offline bundle applied,
    and ``rebuild_offline_manifest`` is idempotent, so proposing it is always safe.
    """
    signals: list[str] = []
    try:
        from apps.platform_runtime.customer_health import calculate_school_health

        status = str(calculate_school_health(school).get("status") or "")
    except Exception:  # noqa: BLE001
        return signals
    if status == "setup_needed":
        signals.append("tenant_offline_unconfigured")
    return signals


def platform_signals() -> list[str]:
    """Conservative platform-scope signals from the live platform-health summary."""
    signals: list[str] = []
    try:
        from apps.platform_runtime.platform_health import platform_health_summary

        if platform_health_summary(use_cache=False).get("level") != "success":
            signals.append("platform_health_degraded")
    except Exception:  # noqa: BLE001
        return signals
    return signals
