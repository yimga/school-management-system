"""
System-level AI suggestions (drafts / structured recommendations only; no auto-action).

Gated by ``RUNMYCAMPUS_AI_ENABLED``; when off, returns rules/deterministic text.
"""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.ai_providers import get_ai_runtime_config, run_ai_prompt
from apps.platform_runtime.customer_health import calculate_school_health
from apps.platform_runtime.onboarding import get_school_onboarding_progress

_LIVE_AI_PROVIDERS = frozenset({"litellm", "ollama"})


def _ai_narrative_or(deterministic: str, text: str, meta: dict[str, Any] | None) -> str:
    """Use the model's narrative ONLY when a live LLM actually answered.

    ``run_ai_prompt`` degrades to a deterministic rules string (``provider="rules"``)
    or a refusal (``provider`` in ``none``/``policy``/``error``/``disabled``) whenever
    no live provider is reachable. Those strings are generic — and the rules fallback
    historically echoed the raw prompt context — so for these structured cards we prefer
    our own deterministic sentence unless the provider was genuinely live.
    """
    provider = str((meta or {}).get("provider") or "").strip().lower()
    narrative = (text or "").strip()
    if provider in _LIVE_AI_PROVIDERS and narrative:
        return narrative
    return deterministic


def structure_ai_recommendation(
    *,
    recommendation_key: str,
    title: str,
    explanation: str,
    confidence: float,
    proposed_action: str,
    requires_approval: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "recommendation_key": recommendation_key[:120],
        "title": title[:500],
        "explanation": explanation[:8000],
        "confidence": max(0.0, min(1.0, float(confidence))),
        "proposed_action": proposed_action[:2000],
        "requires_approval": bool(requires_approval),
        "extra": extra or {},
    }


def generate_school_health_insight(school, user) -> dict[str, Any]:
    """Deterministic + optional LLM narrative from real health metrics."""
    h = calculate_school_health(school)
    expl = (
        f"Onboarding {h.get('onboarding_percent', 0)}%; "
        f"students {h.get('student_count', 0)}; status {h.get('status', 'unknown')}."
    )
    cfg = get_ai_runtime_config(school=school)
    if not cfg.get("enabled"):
        return structure_ai_recommendation(
            recommendation_key="school_health.rules",
            title="School health snapshot",
            explanation=expl,
            confidence=0.75,
            proposed_action="Review onboarding checklist and report schedules in operator tools.",
            requires_approval=True,
            extra={"source": "rules", "health": h},
        )
    text, meta = run_ai_prompt(
        "Summarize school health in 2 sentences for an administrator. No PII.",
        str({k: h.get(k) for k in ("score", "status", "onboarding_percent", "student_count")}),
        school,
        user=user,
        prompt_type="school_health_insight",
        # External-tier declaration (gateway is deny-by-default). SAFE: the
        # context is a literal 4-key projection of calculate_school_health —
        # two integers, one enum-ish status string and one aggregate COUNT.
        # No student row, name, guardian contact or narrative is reachable.
        sensitivity_class="internal",
    )
    return structure_ai_recommendation(
        recommendation_key="school_health.ai",
        title="School health insight",
        explanation=_ai_narrative_or(expl, text, meta),
        confidence=0.5,
        proposed_action="Review before sharing with staff.",
        requires_approval=True,
        extra={"meta": meta, "health": h},
    )


def generate_onboarding_next_action_insight(school, user) -> dict[str, Any]:
    prog = get_school_onboarding_progress(school) if school else {}
    pct = int(prog.get("percent") or 0)
    expl = f"Progress about {pct}%. Complete remaining CCC steps in order."
    if not get_ai_runtime_config().get("enabled"):
        return structure_ai_recommendation(
            recommendation_key="onboarding.rules",
            title="Onboarding progress",
            explanation=expl,
            confidence=0.8,
            proposed_action="Open School activation (CCC) and finish the next incomplete step.",
            requires_approval=True,
            extra={"percent": pct, "source": "rules"},
        )
    text, meta = run_ai_prompt(
        "List one concrete next onboarding action for a school admin in one sentence.",
        str({"percent": pct}),
        school,
        user=user,
        prompt_type="onboarding_next",
        # External-tier declaration (gateway is deny-by-default). SAFE: the
        # entire context is ``{"percent": <int>}`` — ``pct`` is coerced with
        # int() above. Nothing else can enter this prompt.
        sensitivity_class="internal",
    )
    return structure_ai_recommendation(
        recommendation_key="onboarding.ai",
        title="Next onboarding action",
        explanation=_ai_narrative_or(expl, text, meta),
        confidence=0.5,
        proposed_action="Confirm in CCC before acting.",
        requires_approval=True,
        extra={"meta": meta},
    )


def generate_workflow_suggestion(school, user, signal_key: str) -> dict[str, Any]:
    sk = (signal_key or "generic").strip()[:80]
    expl = "Review scheduled reports and letter templates; ensure staff roles are assigned."
    if not get_ai_runtime_config(school=school).get("enabled"):
        return structure_ai_recommendation(
            recommendation_key=f"workflow.{sk}.rules",
            title="Workflow hygiene",
            explanation=expl,
            confidence=0.6,
            proposed_action="Open Studio automation or scheduled reports hub.",
            requires_approval=True,
            extra={"signal_key": sk, "source": "rules"},
        )
    text, meta = run_ai_prompt(
        "Give one practical workflow improvement for a school; no claims of execution.",
        f"signal_key={sk}",
        school,
        user=user,
        prompt_type="workflow_suggestion",
    )
    return structure_ai_recommendation(
        recommendation_key=f"workflow.{sk}.ai",
        title="Workflow suggestion",
        explanation=_ai_narrative_or(expl, text, meta),
        confidence=0.45,
        proposed_action="Validate in Studio before enabling automation.",
        requires_approval=True,
        extra={"meta": meta, "signal_key": sk},
    )


def generate_anomaly_risk_nudge(school, user) -> dict[str, Any] | None:
    """
    Lightweight risk / anomaly hint from aggregated health only (no student rows).
    Returns None when status is healthy enough that no nudge is useful.
    """
    if school is None:
        return None
    h = calculate_school_health(school)
    status = str(h.get("status") or "")
    score = int(h.get("score") or 0)
    if status in ("healthy", "power_user") and score >= 70:
        return None
    expl = (
        f"Signals: status={status}, score={score}, onboarding "
        f"{h.get('onboarding_percent', 0)}%, reports_scheduled="
        f"{h.get('has_report_schedules', False)}."
    )
    cfg = get_ai_runtime_config(school=school)
    if not cfg.get("enabled"):
        return structure_ai_recommendation(
            recommendation_key="anomaly_risk.rules",
            title="Operational risk nudge",
            explanation=expl + " Review CCC onboarding and scheduled reporting.",
            confidence=0.72,
            proposed_action="Open operator dashboard and complete open onboarding steps.",
            requires_approval=True,
            extra={"source": "rules", "health": h},
        )
    text, meta = run_ai_prompt(
        "From aggregated school metrics only (no individual students), give one risk-aware "
        "nudge for an administrator in two sentences. Do not invent incidents.",
        str(
            {
                "status": status,
                "score": score,
                "onboarding_percent": h.get("onboarding_percent"),
                "has_report_schedules": h.get("has_report_schedules"),
            }
        ),
        school,
        user=user,
        prompt_type="anomaly_risk_nudge",
        content_sensitivity="standard",
        # External-tier declaration (gateway is deny-by-default). SAFE: the
        # context is a literal 4-key dict of aggregates — status (enum-ish),
        # score (int), onboarding_percent (int), has_report_schedules (bool).
        # No individual student/guardian row is reachable from this prompt.
        sensitivity_class="internal",
    )
    return structure_ai_recommendation(
        recommendation_key="anomaly_risk.ai",
        title="Operational risk nudge",
        explanation=_ai_narrative_or(expl, text, meta),
        confidence=0.48,
        proposed_action="Validate against live data before acting.",
        requires_approval=True,
        extra={"meta": meta, "health": h},
    )


def create_ai_recommendation_record(_payload: dict[str, Any]) -> None:
    """No persistent model in product yet; reserved for future opt-in storage."""
    return None


def list_ai_recommendation_keys() -> list[str]:
    """
    Return sorted recommendation keys from the central registry.
    Local import avoids module cycles during startup.
    """
    from apps.platform_runtime.ai_recommendation_registry import (
        get_registered_ai_recommendations,
    )

    return sorted(get_registered_ai_recommendations().keys())
