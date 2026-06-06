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


def _resolve_user(user, teacher):
    if user is not None:
        return user
    if teacher is not None:
        return getattr(teacher, "user", None)
    return None


def _safe_invoke(
    task_type,
    prompt: str,
    *,
    school,
    user=None,
    teacher=None,
    user_query: str = "",
) -> tuple[str, dict[str, Any]]:
    from services.ai_copilot_rbac import invoke_service_layer_ai

    actor = _resolve_user(user, teacher)
    text, meta = invoke_service_layer_ai(
        user=actor,
        school=school,
        task_type=task_type,
        prompt=prompt,
        user_query=user_query,
        surface="teacher_lesson_plan",
    )
    if meta.get("outcome") == "permission_refusal":
        return "", meta
    return (text or "").strip() if isinstance(text, str) else "", meta or {}


def draft_lesson_plan_outline(
    *,
    school,
    teacher,
    subject: str,
    grade_level: str,
    intent: str,
    objectives: Iterable[str] | None = None,
    user=None,
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
        TaskType.WORKFLOW_DRAFT,
        prompt,
        school=school,
        user=user,
        teacher=teacher,
        user_query=intent,
    )
    if text and len(text) > MAX_OUTLINE_CHARS:
        text = text[: MAX_OUTLINE_CHARS - 1].rstrip() + "…"
    return text, meta
