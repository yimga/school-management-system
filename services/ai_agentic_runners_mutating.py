"""Wave Q3 (v3.95.2 — 2026-05-26) — Mutating agentic AI sample runners.

**OPT-IN ONLY.** Operators wire these into ``execute_action`` explicitly per
surface. They are NOT auto-registered in
``ai_agentic_runners._RUNNERS`` — that's the deliberate review gate.

Importing this module does NOT change any global state. Each runner is a
plain function that the caller passes via ``runner=`` to ``execute_action``.
The kernel's permission verifier + confirmation gate ensure these never run
without an explicit ``ctx.confirmed_by``.

Boundaries:
- All runners are tenant-scoped via ``ctx.tenant_id``.
- No raw exception leaks — the kernel wraps the call in try/except, so any
  exception here is captured and returned as ``ExecutionResult.error``.
- All mutations are logged with ``ctx.user_id`` (hashed in the audit_sink).
"""

from __future__ import annotations

import logging
from typing import Any

from .ai_agentic import ActionContext, ProposedAction


logger = logging.getLogger(__name__)


def _scope_school(tenant_id: str):
    """Resolve the School row for tenant-scoped writes. Returns None when
    the tenant can't be resolved (which the runner must treat as a no-op)."""
    try:
        from apps.schools.models import School  # type: ignore
        if tenant_id.isdigit():
            return School.objects.filter(id=int(tenant_id)).first()
        return School.objects.filter(slug=tenant_id).first()
    except Exception as exc:  # noqa: BLE001
        logger.warning("scope_school lookup failed tenant=%s err=%s",
                       tenant_id, exc)
        return None


# ---------------------------------------------------------------------------
# send_parent_message — pushes through existing communication channel adapter
# ---------------------------------------------------------------------------

def run_send_parent_message(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Send a message to a parent through the configured channel.

    Params: ``parent_id`` (Guardian PK), ``channel`` (whatsapp/sms/email),
    ``body`` (str, max 1500 chars).
    """
    params = proposed.params or {}
    parent_id = str(params.get("parent_id") or "")
    channel = str(params.get("channel") or "whatsapp").lower()
    body = str(params.get("body") or "")[:1500]

    if not parent_id or not body:
        return {"ok": False, "error": "parent_id and body required"}

    school = _scope_school(ctx.tenant_id)
    if school is None:
        return {"ok": False, "error": "tenant scope unavailable"}

    try:
        from apps.people.models import Guardian  # type: ignore
        guardian = Guardian.objects.filter(school=school, pk=parent_id).first()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"guardian lookup failed: {exc}"}
    if guardian is None:
        return {"ok": False, "error": f"guardian {parent_id} not found in tenant"}

    # Route through the existing channel adapter facade (Wave v2.7+).
    try:
        from apps.communication.channel_adapter import (  # type: ignore
            ChannelAddress, ChannelMessage, send_message,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"channel adapter unavailable: {exc}"}

    # Pick the right address per channel.
    if channel == "email":
        address_str = getattr(guardian, "email", "") or ""
    else:
        address_str = (
            getattr(guardian, "phone_e164", None)
            or getattr(guardian, "phone", None)
            or getattr(guardian, "mobile", None)
            or ""
        )
    if not address_str:
        return {"ok": False,
                "error": f"guardian {parent_id} has no {channel} address"}

    try:
        result = send_message(
            tenant_id=str(school.pk),
            address=ChannelAddress(channel=channel, address=address_str,
                                    locale=str(getattr(guardian, "locale", "en") or "en")),
            message=ChannelMessage(
                subject="School update",
                body_text=body,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"send failed: {exc}"}

    return {
        "ok": bool(getattr(result, "success", False)),
        "channel": getattr(result, "channel", channel),
        "adapter_id": getattr(result, "adapter_id", ""),
        "detail": getattr(result, "detail", ""),
    }


# ---------------------------------------------------------------------------
# mark_student_absent — write an attendance record for today
# ---------------------------------------------------------------------------

def run_mark_student_absent(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Mark a student absent for today (or a given date).

    Params: ``student_id`` (PK), ``date`` (YYYY-MM-DD, default today),
    ``reason`` (str, max 240 chars).
    """
    params = proposed.params or {}
    student_id = str(params.get("student_id") or "")
    if not student_id:
        return {"ok": False, "error": "student_id required"}
    reason = str(params.get("reason") or "agentic-flagged")[:240]

    from datetime import date as _date
    raw_date = params.get("date")
    try:
        if raw_date:
            year, month, day = (int(x) for x in str(raw_date).split("-"))
            on_date = _date(year, month, day)
        else:
            on_date = _date.today()
    except (TypeError, ValueError):
        return {"ok": False, "error": f"invalid date {raw_date!r}"}

    school = _scope_school(ctx.tenant_id)
    if school is None:
        return {"ok": False, "error": "tenant scope unavailable"}

    try:
        from apps.people.models import Student  # type: ignore
        from apps.academics.models import AttendanceRecord  # type: ignore
        student = Student.objects.filter(school=school, pk=student_id).first()
        if student is None:
            return {"ok": False,
                    "error": f"student {student_id} not found in tenant"}
        # Upsert: today's record may already exist (mark present earlier).
        rec, created = AttendanceRecord.objects.update_or_create(
            student=student,
            date=on_date,
            defaults={
                "status": "absent",
                "notes": reason,
                "school": school,
            },
        )
        return {"ok": True, "created": created,
                "attendance_id": rec.pk,
                "student": str(student),
                "date": on_date.isoformat()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"attendance write failed: {exc}"}


# ---------------------------------------------------------------------------
# schedule_parent_callback — append to office callback queue
# ---------------------------------------------------------------------------

def run_schedule_parent_callback(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Add a parent-callback entry to the school office queue.

    Schools rarely have a first-class CallbackQueue model — this runner
    writes to a JSON ledger on ``School.settings["callback_queue"]``,
    capped at 200 entries (FIFO).

    Params: ``parent_id`` (Guardian PK or just a free-form contact),
    ``preferred_time`` (ISO datetime str, optional).
    """
    params = proposed.params or {}
    parent_id = str(params.get("parent_id") or "")
    preferred_time = str(params.get("preferred_time") or "")
    if not parent_id:
        return {"ok": False, "error": "parent_id required"}

    school = _scope_school(ctx.tenant_id)
    if school is None:
        return {"ok": False, "error": "tenant scope unavailable"}

    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    queue = settings.get("callback_queue")
    if not isinstance(queue, list):
        queue = []

    entry = {
        "parent_id": parent_id,
        "preferred_time": preferred_time,
        "requested_by_user_id": ctx.user_id,
        "agentic_audit_required": True,
    }
    queue.append(entry)
    # Cap to 200 (FIFO).
    if len(queue) > 200:
        queue = queue[-200:]
    settings["callback_queue"] = queue
    try:
        school.settings = settings
        school.save(update_fields=["settings"])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"school.settings write failed: {exc}"}

    return {"ok": True, "queue_size": len(queue),
            "position": len(queue), "entry": entry}


# ---------------------------------------------------------------------------
# Opt-in lookup (operators import this map and pick what to enable)
# ---------------------------------------------------------------------------

OPT_IN_MUTATING_RUNNERS: dict[str, Any] = {
    "send_parent_message": run_send_parent_message,
    "mark_student_absent": run_mark_student_absent,
    "schedule_parent_callback": run_schedule_parent_callback,
}
