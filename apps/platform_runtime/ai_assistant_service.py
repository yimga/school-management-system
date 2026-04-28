"""
North Star SLICE 11 — AI assistant drafts (no auto-send, no silent DB writes).

All outputs are DRAFTS; operators must review and explicitly approve before any action.
"""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.ai_providers import run_ai_prompt

# Re-export for tests
__all__ = [
    "generate_parent_message",
    "generate_report_summary",
    "generate_school_insights",
    "suggest_next_actions",
    "draft_configuration_copilot",
    "draft_report_comment_assistant",
    "draft_policy_assistant",
    "draft_workflow_builder_assistant",
    "draft_support_knowledge_assistant",
    "log_northstar_ai_audit",
    "NorthstarDraftResult",
]


class NorthstarDraftResult(dict):
    """draft_text, requires_approval, meta, ok flags."""

    def __init__(
        self,
        *,
        draft_text: str = "",
        requires_approval: bool = True,
        meta: dict[str, Any] | None = None,
        ok: bool = True,
    ):
        super().__init__(
            draft_text=draft_text,
            requires_approval=requires_approval,
            meta=meta or {},
            ok=ok,
        )

    @property
    def draft_text(self) -> str:
        return str(self.get("draft_text") or "")

    @property
    def requires_approval(self) -> bool:
        return bool(self.get("requires_approval", True))

    @property
    def meta(self) -> dict[str, Any]:
        return self.get("meta") or {}


def _tenant_safe_student_label(student) -> str:
    """Minimize PII in prompts; use first name + last initial when possible."""
    if student is None:
        return "the student"
    fn = (getattr(student, "first_name", None) or "").strip() or "Student"
    ln = (getattr(student, "last_name", None) or "").strip()
    if ln:
        return f"{fn} {ln[0]}."
    return fn


def log_northstar_ai_audit(
    *,
    action_type: str,
    school,
    user,
    outcome: str,
    meta: dict[str, Any],
    draft_char_count: int = 0,
) -> None:
    """
    Persist metadata-only audit (no raw student text in payload).
    """
    try:
        from apps.platform_runtime.models import AIActionAuditLog
    except ImportError:
        return
    try:
        tid = school.pk if school is not None else None
        uid = getattr(user, "pk", None) if user is not None else None
        safe_payload = {
            "outcome": outcome,
            "provider": (meta or {}).get("provider"),
            "task_type": (meta or {}).get("task_type"),
            "draft_char_count": int(draft_char_count),
            "prompt_type": action_type,
            "northstar_slice": 11,
        }
        if (meta or {}).get("prompt_injection_blocked"):
            safe_payload["blocked"] = "prompt_injection"
        AIActionAuditLog.objects.create(
            action_type=action_type[:80],
            tenant_id=tid,
            user_id=uid,
            request_id=str((meta or {}).get("request_id") or "")[:64],
            payload=safe_payload,
        )
    except Exception:  # noqa: BLE001
        return


def generate_parent_message(
    student,
    context: dict[str, Any] | None,
    *,
    school,
    user,
) -> NorthstarDraftResult:
    """
    Draft a parent-facing message. Does not send email or post to messaging APIs.
    """
    ctx = context if isinstance(context, dict) else {}
    label = _tenant_safe_student_label(student)
    topic = str(ctx.get("topic") or "a school update").strip()
    prompt = (
        "You are helping a school staff member write a short, professional message to a parent. "
        "Output only the message body text, no subject line, no meta-commentary. "
        "Use a warm but formal tone. Do not include private student ID numbers."
    )
    context_blob = f"Student reference: {label}. Topic: {topic}. Notes: {ctx.get('notes', '')!s}"
    text, meta = run_ai_prompt(
        prompt,
        context_blob,
        school,
        user=user,
        prompt_type="parent_message",
    )
    log_northstar_ai_audit(
        action_type="parent_message",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(
        draft_text=text or "",
        requires_approval=True,
        meta=meta,
        ok=True,
    )


def generate_report_summary(
    student,
    report_data: dict[str, Any] | None,
    *,
    school,
    user,
) -> NorthstarDraftResult:
    """Draft a short summary of report data for operator review (not a final report card)."""
    ctx = report_data if isinstance(report_data, dict) else {}
    label = _tenant_safe_student_label(student)
    # Only pass non-sensitive keys as strings
    safe_bits = {k: str(v)[:200] for k, v in list(ctx.items())[:12]}
    prompt = (
        "Summarize the following structured report hints for a teacher in 2-4 short bullet points. "
        "Do not invent grades; if data is missing, say so. Output plain text."
    )
    context_blob = f"Student: {label}. Data: {safe_bits!r}"
    text, meta = run_ai_prompt(
        prompt,
        context_blob,
        school,
        user=user,
        prompt_type="report_summary",
    )
    log_northstar_ai_audit(
        action_type="report_summary",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(
        draft_text=text or "",
        requires_approval=True,
        meta=meta,
        ok=True,
    )


def generate_school_insights(
    school_metrics: dict[str, Any] | None,
    *,
    school,
    user,
) -> NorthstarDraftResult:
    """Draft operational insights from aggregated metrics only (no individual students)."""
    m = school_metrics if isinstance(school_metrics, dict) else {}
    safe = {k: str(v)[:80] for k, v in list(m.items())[:20]}
    prompt = (
        "Given aggregated school metrics only (no personal data), suggest 3 concise operational "
        "insights an administrator could investigate. Plain text bullets."
    )
    context_blob = f"Metrics: {safe!r}"
    text, meta = run_ai_prompt(
        prompt,
        context_blob,
        school,
        user=user,
        prompt_type="school_insights",
    )
    log_northstar_ai_audit(
        action_type="school_insights",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(
        draft_text=text or "",
        requires_approval=True,
        meta=meta,
        ok=True,
    )


def suggest_next_actions(
    school,
    *,
    user,
    snapshot: dict[str, Any] | None = None,
) -> NorthstarDraftResult:
    """Draft suggested next onboarding/configuration actions (not executed)."""
    snap = snapshot if isinstance(snapshot, dict) else {}
    prompt = (
        "List up to 5 practical next actions for a school administrator improving reporting "
        "and scheduling hygiene. One line each. Do not claim actions were performed."
    )
    context_blob = f"Optional snapshot keys: {list(snap.keys())[:15]!r}"
    text, meta = run_ai_prompt(
        prompt,
        context_blob,
        school,
        user=user,
        prompt_type="next_actions",
    )
    log_northstar_ai_audit(
        action_type="next_actions",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(
        draft_text=text or "",
        requires_approval=True,
        meta=meta,
        ok=True,
    )


def _sanitize_policy_excerpt(raw: str, *, limit: int = 1200) -> str:
    return (raw or "").strip()[:limit]


def draft_configuration_copilot(
    hints: dict[str, Any] | None,
    *,
    school,
    user,
) -> NorthstarDraftResult:
    """CCC-style setup guidance from structured non-PII keys only."""
    h = hints if isinstance(hints, dict) else {}
    keys = [str(k) for k in list(h.keys())[:24]]
    prompt = (
        "You help school administrators with configuration. Given only section/key names "
        "and non-identifying status flags, propose a concise checklist (max 5 bullets). "
        "Do not claim settings were changed."
    )
    blob = f"Sections/keys: {keys!r}. Values omitted for privacy."
    text, meta = run_ai_prompt(prompt, blob, school, user=user, prompt_type="config_copilot")
    log_northstar_ai_audit(
        action_type="config_copilot",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(draft_text=text or "", requires_approval=True, meta=meta, ok=True)


def draft_report_comment_assistant(
    cues: dict[str, Any] | None,
    *,
    school,
    user,
) -> NorthstarDraftResult:
    """Draft narrative comments for reports using coarse cues (term label, subject area)."""
    c = cues if isinstance(cues, dict) else {}
    term = str(c.get("term_label") or c.get("term") or "current term").strip()[:80]
    area = str(c.get("subject_area") or "general").strip()[:80]
    prompt = (
        "Draft 2-3 short neutral sentences suitable as administrator commentary on a "
        "term report context. Do not include student names or IDs."
    )
    blob = (
        f"Term context: {term}. Subject area: {area}. Notes (truncated): "
        f"{_sanitize_policy_excerpt(str(c.get('notes', '')), limit=400)}"
    )
    text, meta = run_ai_prompt(prompt, blob, school, user=user, prompt_type="report_comment")
    log_northstar_ai_audit(
        action_type="report_comment",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(draft_text=text or "", requires_approval=True, meta=meta, ok=True)


def draft_policy_assistant(
    excerpt: str,
    *,
    school,
    user,
    topic: str = "",
) -> NorthstarDraftResult:
    """Policy wording hints from a tenant-supplied excerpt (operator-reviewed)."""
    safe_excerpt = _sanitize_policy_excerpt(excerpt)
    tp = (topic or "school policy").strip()[:120]
    prompt = (
        "Suggest clearer wording for an internal policy excerpt. Output bullet points only. "
        "Do not assert legal compliance."
    )
    blob = f"Topic: {tp}. Excerpt:\n{safe_excerpt}"
    text, meta = run_ai_prompt(prompt, blob, school, user=user, prompt_type="policy_assistant")
    log_northstar_ai_audit(
        action_type="policy_assistant",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(draft_text=text or "", requires_approval=True, meta=meta, ok=True)


def draft_workflow_builder_assistant(
    intent: dict[str, Any] | None,
    *,
    school,
    user,
) -> NorthstarDraftResult:
    """Structured workflow scaffolding suggestion — never executes automation."""
    it = intent if isinstance(intent, dict) else {}
    goal = str(it.get("goal") or "improve reporting hygiene").strip()[:200]
    prompt = (
        "Outline at most 4 steps to improve school workflows (reports, letters, schedules). "
        "Explicitly state that automation must be approved in-product. Plain text bullets."
    )
    blob = f"Goal hint: {goal}. Constraints: no execution."
    text, meta = run_ai_prompt(prompt, blob, school, user=user, prompt_type="workflow_builder")
    log_northstar_ai_audit(
        action_type="workflow_builder",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(draft_text=text or "", requires_approval=True, meta=meta, ok=True)


def draft_support_knowledge_assistant(
    query_context: dict[str, Any] | None,
    *,
    school,
    user,
) -> NorthstarDraftResult:
    """Support-style hints using aggregates / topic only (no roster exports)."""
    q = query_context if isinstance(query_context, dict) else {}
    topic = str(q.get("topic") or "platform usage").strip()[:120]
    prompt = (
        "Provide internal support-style hints for school staff using only the topic provided. "
        "Do not reference individual students."
    )
    blob = f"Topic: {topic}. Scope: aggregated guidance only."
    text, meta = run_ai_prompt(prompt, blob, school, user=user, prompt_type="support_knowledge")
    log_northstar_ai_audit(
        action_type="support_knowledge",
        school=school,
        user=user,
        outcome=meta.get("provider", "unknown"),
        meta=meta,
        draft_char_count=len(text or ""),
    )
    return NorthstarDraftResult(draft_text=text or "", requires_approval=True, meta=meta, ok=True)
