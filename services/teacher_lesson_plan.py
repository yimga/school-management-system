"""
Teacher lesson-plan outline drafts (batch 1396 — education pack gear 2).

Draft-only: teachers review before uploading to lesson-plan storage.
Uses ``TaskType.WORKFLOW_DRAFT`` — same tier policy as playbooks.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 4000
MAX_OUTLINE_CHARS = 2500


def _safe_invoke(task_type, prompt: str, *, school, user_query: str = "") -> tuple[str, dict[str, Any]]:
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
                "sensitivity_class": "medium",
                "audit_feature": "lesson_plan_outline",
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("teacher_lesson_plan: gateway raised %s", exc)
        return "", {"error": str(exc)[:200], "provider": "none"}
    return (result or "").strip() if isinstance(result, str) else "", meta or {}


def draft_lesson_plan_outline(
    *,
    school,
    teacher,
    subject: str,
    grade_level: str,
    intent: str,
    objectives: Iterable[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Produce a structured lesson outline (objectives, flow, assessment)."""
    teacher_name = getattr(teacher, "get_full_name", lambda: "")() or getattr(
        teacher, "username", "the teacher"
    )
    school_name = getattr(school, "name", "the school")
    obj_lines = "\n".join(f"- {o}" for o in (objectives or []) if o) or "- (none provided)"
    prompt = (
        f"You are helping {teacher_name} at {school_name} draft a lesson plan outline.\n"
        f"Subject: {subject or 'general'}\n"
        f"Grade / level: {grade_level or 'mixed'}\n"
        f"Teacher focus: {intent}\n"
        f"Learning objectives:\n{obj_lines}\n\n"
        "Write a concise outline with sections: Learning objectives (3 bullets), "
        "Warm-up (2 sentences), Core activity (4 bullets), Differentiation (2 bullets), "
        "Formative check (1 question), Homework/extension (optional). "
        "Use plain text headings, no markdown code fences. Tenant-safe — no student PII.\n"
    )[:MAX_PROMPT_CHARS]

    try:
        from services.ai_gateway import TaskType
    except ImportError:
        return "", {"error": "ai_gateway TaskType unavailable"}
    text, meta = _safe_invoke(
        TaskType.WORKFLOW_DRAFT, prompt, school=school, user_query=intent
    )
    if text and len(text) > MAX_OUTLINE_CHARS:
        text = text[: MAX_OUTLINE_CHARS - 1].rstrip() + "…"
    return text, meta
