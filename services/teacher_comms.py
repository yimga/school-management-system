"""
Pass 13.B: teacher communication assistant — draft messages, never send.

Mirrors the draft-and-approve pattern from apps/evals/narrative_feedback.py.
Two surfaces:

  - draft_parent_message(school, teacher, student, intent, key_facts) →
      a 80-120 word parent-facing message draft, tone-matched to the school
      (warm, factual, no speculation). The caller hands the draft to the
      teacher to review before send.

  - draft_report_card_comment(school, teacher, student, term, evaluations) →
      a 40-60 word per-term comment for the report card. Same approval gate.

Both return (text, meta). Both fail closed: on any error / disabled feature,
they return ("", {"error": ...}) so the UI can fall back to "no draft
available — write your own".

Entitlement gate (`apps.billing.entitlements.can`) is the caller's job — these
helpers just route through the AI gateway with the right TaskType.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 4000
MAX_PARENT_MESSAGE_CHARS = 1500
MAX_REPORT_COMMENT_CHARS = 500


def _student_display_name(student) -> str:
    return (
        getattr(student, "display_name", None)
        or f"{getattr(student, 'first_name', '')} {getattr(student, 'last_name', '')}".strip()
        or "the student"
    )


def _safe_invoke(task_type, prompt: str, *, school, user_query: str = "") -> tuple[str, dict[str, Any]]:
    """Wrap invoke() so callers never see a raised exception."""
    try:
        from services.ai_gateway import invoke
    except ImportError:
        return "", {"error": "ai_gateway unavailable", "provider": "none"}
    try:
        result, meta = invoke(
            task_type,
            prompt,
            user_query=user_query,
            metadata={
                "school_id": str(getattr(school, "id", "") or ""),
                "tenant_id": str(getattr(school, "id", "") or ""),
                "sensitivity_class": "high",
            },
        )
    except Exception as exc:  # noqa: BLE001 - any error becomes a closed-fail
        logger.warning("teacher_comms: gateway raised %s", exc)
        return "", {"error": str(exc)[:200], "provider": "none"}
    return (result or "").strip() if isinstance(result, str) else "", meta or {}


def draft_parent_message(
    *,
    school,
    teacher,
    student,
    intent: str,
    key_facts: Iterable[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Produce a draft parent-facing message. `intent` is one short clause from
    the teacher (e.g. "behavior concern in math last week"). `key_facts` is
    an optional iterable of one-line observations.
    """
    teacher_name = getattr(teacher, "get_full_name", lambda: "")() or getattr(
        teacher, "username", "your teacher"
    )
    student_name = _student_display_name(student)
    facts = "\n".join(f"- {fact}" for fact in (key_facts or []) if fact)
    if not facts:
        facts = "- (no additional observations provided)"

    prompt = (
        f"You are drafting a short message from {teacher_name} to {student_name}'s "
        f"parent at {getattr(school, 'name', 'the school')}.\n"
        f"Teacher's intent: {intent}\n"
        f"Observations:\n{facts}\n\n"
        "Write a warm, factual, 80-120 word draft. Open with the student's name, "
        "describe one specific observation, suggest one concrete next step. Do not "
        "speculate about home life or medical history. End with a one-line invitation "
        "to reply. Plain prose. No bullet points, no headings, no signature line.\n"
    )[:MAX_PROMPT_CHARS]

    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return "", {"error": "ai_gateway TaskType unavailable"}
    text, meta = _safe_invoke(TaskType.TEACHER_COMMS_DRAFT, prompt, school=school, user_query=intent)
    if text and len(text) > MAX_PARENT_MESSAGE_CHARS:
        text = text[: MAX_PARENT_MESSAGE_CHARS - 1].rstrip() + "…"
    return text, meta


def draft_report_card_comment(
    *,
    school,
    teacher,
    student,
    term_name: str,
    evaluations: Iterable[dict] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Produce a 40-60 word report-card comment summarizing the term. The caller
    is expected to provide a small evaluations iterable of dicts like
    {"subject": "Math", "score": 78, "trend": "+5"} so the LLM has signal
    without needing direct ORM access.
    """
    teacher_name = getattr(teacher, "get_full_name", lambda: "")() or getattr(
        teacher, "username", "Teacher"
    )
    student_name = _student_display_name(student)
    rows = []
    for ev in (evaluations or [])[:8]:
        subject = str(ev.get("subject") or "")[:60]
        score = str(ev.get("score") or "")[:8]
        trend = str(ev.get("trend") or "")[:8]
        rows.append(f"- {subject}: score {score} (trend {trend})" if subject else "")
    facts_block = "\n".join(r for r in rows if r) or "- (no evaluations available)"

    prompt = (
        f"You are drafting a report-card comment from {teacher_name} for "
        f"{student_name} at {getattr(school, 'name', 'the school')} — term: {term_name}.\n"
        f"Evaluation snapshot:\n{facts_block}\n\n"
        "Write 40-60 words, plain prose, no bullet points or headings. Mention one "
        "subject strength and one focus area for next term. Forward-looking, factual, "
        "warm but professional. Don't invent grades or events not in the snapshot.\n"
    )[:MAX_PROMPT_CHARS]

    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return "", {"error": "ai_gateway TaskType unavailable"}
    text, meta = _safe_invoke(
        TaskType.REPORT_CARD_COMMENT, prompt, school=school, user_query=term_name
    )
    if text and len(text) > MAX_REPORT_COMMENT_CHARS:
        text = text[: MAX_REPORT_COMMENT_CHARS - 1].rstrip() + "…"
    return text, meta
