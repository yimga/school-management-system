"""
Pass 13: LLM-explained at-risk `reason_summary`.

The heuristic reason ("Average score over the last 30 days is N") is the source
of truth — it survives even when the LLM is unavailable. This helper layers a
1-2 sentence human-readable explanation on top:

    "Maya's term-2 average dropped 12 points after her grandmother's funeral
     leave; flag for counselor follow-up before week-3 quizzes."

It calls the AI gateway with TaskType.RISK_EXPLAIN. The gateway's tier policy
prefers Anthropic Claude when premium is allowed, then Ollama, then rules.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cap the prompt size so we never blow past Claude's context window even when
# a student has thousands of evaluations in their history.
MAX_PROMPT_CHARS = 4000
MAX_REASON_CHARS = 500


def explain_risk(
    *,
    school,
    student,
    score: float,
    heuristic_reason: str,
    facts: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Generate a short, school-context-aware explanation of why this student was
    flagged. Returns (reason, meta). On any failure the heuristic_reason is
    returned unchanged with meta.error set.
    """
    if not heuristic_reason:
        heuristic_reason = f"Risk score {round(float(score), 1)} above the threshold."

    facts = facts or {}
    student_name = (
        getattr(student, "display_name", None)
        or f"{getattr(student, 'first_name', '')} {getattr(student, 'last_name', '')}".strip()
        or "the student"
    )

    prompt = _build_prompt(
        school_name=getattr(school, "name", "the school"),
        student_name=student_name,
        score=score,
        heuristic_reason=heuristic_reason,
        facts=facts,
    )

    try:
        from services.ai_gateway import TaskType, invoke
    except ImportError:
        return heuristic_reason, {"error": "ai_gateway unavailable", "provider": "none"}

    try:
        result, meta = invoke(
            TaskType.RISK_EXPLAIN,
            prompt,
            user_query=heuristic_reason,
            metadata={
                "school_id": str(getattr(school, "id", "") or ""),
                "tenant_id": str(getattr(school, "id", "") or ""),
                "sensitivity_class": "high",  # student names + scores are PII
            },
        )
    except Exception as exc:  # noqa: BLE001 - gateway must never break nightly compute
        logger.warning("explain_risk: gateway raised %s", exc)
        return heuristic_reason, {"error": str(exc)[:200], "provider": "none"}

    text = (result or "").strip() if isinstance(result, str) else ""
    if not text:
        return heuristic_reason, {**meta, "fallback_to_heuristic": True}

    # Don't let a chatty LLM blow past the RiskFactor.reason_summary CharField cap.
    if len(text) > MAX_REASON_CHARS:
        text = text[: MAX_REASON_CHARS - 1].rstrip() + "…"
    return text, meta


def _build_prompt(
    *,
    school_name: str,
    student_name: str,
    score: float,
    heuristic_reason: str,
    facts: dict[str, Any],
) -> str:
    """One short, deterministic prompt — no chain-of-thought, no system message."""
    facts_block = "\n".join(f"- {k}: {v}" for k, v in facts.items() if v not in (None, ""))
    if not facts_block:
        facts_block = "- (no additional signals provided)"

    prompt = (
        f"You are an educator's brief, factual at-risk explainer for {school_name}.\n"
        f"Student: {student_name}\n"
        f"Computed risk score: {round(float(score), 1)} out of 100\n"
        f"Heuristic reason: {heuristic_reason}\n"
        f"Supporting signals:\n{facts_block}\n\n"
        "Write one or two sentences (max 60 words) that an administrator can put in\n"
        "front of a teacher or counselor. Focus on observable patterns, never speculate\n"
        "about home life, medical history, or protected attributes. Plain prose, no\n"
        "bullet points, no headings.\n"
    )
    return prompt[:MAX_PROMPT_CHARS]
