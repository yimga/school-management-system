"""
Apply field_capture workflows server-side (batch 1509).

When offline clients queue ``notes_report`` with a JSON body
``{workflow, fields, ...}``, replay runs the same service modules as the
live Django forms (substitute handover, lost-belongings mint/recover) instead
of only persisting opaque text.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

WORKFLOW_SUBSTITUTE_HANDOVER = "substitute_handover"
WORKFLOW_LOST_BELONGINGS_MINT = "lost_belongings_mint"
WORKFLOW_LOST_BELONGINGS_RECOVER = "lost_belongings_recover"

# Finance + payroll workflows delegate to domain handlers (batch 1511).


def _client_offline_id(payload: dict[str, Any]) -> str:
    return str(
        payload.get("client_offline_id")
        or payload.get("idempotency_key")
        or "",
    )[:128]


def parse_field_capture_body(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("body")
    if not raw:
        return None
    try:
        data = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    workflow = (data.get("workflow") or "").strip()
    fields = data.get("fields")
    if not workflow or not isinstance(fields, dict):
        return None
    return {
        "workflow": workflow,
        "fields": fields,
        "captured_at": data.get("captured_at"),
        "page_path": data.get("page_path"),
    }


def try_apply_field_capture_workflow(
    school_id: int,
    user_id: int,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Return apply result when handled; ``None`` → fall through to generic note."""
    parsed = parse_field_capture_body(payload)
    if not parsed:
        return None
    workflow = parsed["workflow"]
    fields = parsed["fields"]
    if workflow == WORKFLOW_SUBSTITUTE_HANDOVER:
        return _apply_substitute_handover_capture(school_id, user_id, fields, payload)
    if workflow == WORKFLOW_LOST_BELONGINGS_MINT:
        return _apply_lost_belongings_mint_capture(school_id, user_id, fields, payload)
    if workflow == WORKFLOW_LOST_BELONGINGS_RECOVER:
        return _apply_lost_belongings_recover_capture(school_id, user_id, fields, payload)
    from apps.finance.offline_workflow_handlers import apply_finance_workflow

    finance_result = apply_finance_workflow(
        school_id, user_id, workflow, fields, payload
    )
    if finance_result is not None:
        if finance_result.get("ok"):
            note_result = _persist_workflow_note(
                school_id,
                user_id,
                payload,
                title=f"{workflow} (offline)",
                body_obj={"workflow": workflow, **finance_result},
            )
            if not note_result.get("ok"):
                return note_result
            return {**note_result, **finance_result}
        return finance_result
    from apps.payroll.offline_workflow_handlers import apply_payroll_workflow

    payroll_result = apply_payroll_workflow(
        school_id, user_id, workflow, fields, payload
    )
    if payroll_result is not None:
        if payroll_result.get("ok"):
            note_result = _persist_workflow_note(
                school_id,
                user_id,
                payload,
                title=f"{workflow} (offline)",
                body_obj={"workflow": workflow, **payroll_result},
            )
            if not note_result.get("ok"):
                return note_result
            return {**note_result, **payroll_result}
        return payroll_result
    # Person creation (edge/LAN offline onboarding). The handler creates the real
    # record (StudentProfile), so we return its result directly — no opaque note.
    from apps.people.offline_workflow_handlers import apply_people_workflow

    people_result = apply_people_workflow(
        school_id, user_id, workflow, fields, payload
    )
    if people_result is not None:
        return people_result
    return None


def _persist_workflow_note(
    school_id: int,
    user_id: int,
    payload: dict[str, Any],
    *,
    title: str,
    body_obj: dict[str, Any],
) -> dict[str, Any]:
    from apps.platform_runtime.offline_queue import _persist_student_note

    enriched = dict(payload)
    enriched["body"] = json.dumps(body_obj, sort_keys=True)
    enriched["title"] = title[:200]
    enriched.setdefault("kind", "note")
    return _persist_student_note(school_id, user_id, enriched)


def _apply_substitute_handover_capture(
    school_id: int,
    user_id: int,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    from apps.schoolops.forms_substitute_handover import SubstituteHandoverForm
    from apps.schoolops.substitute_handover import (
        SubstituteHandoverError,
        TeacherAbsenceTrigger,
        build_packet,
    )

    form = SubstituteHandoverForm(data=fields)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    cleaned = form.cleaned_data
    expose_medical = bool(cleaned.get("expose_medical_iep"))
    try:
        trigger = TeacherAbsenceTrigger(
            tenant_id=str(school_id),
            teacher_id=cleaned["teacher_id"],
            absence_start=cleaned["absence_start"],
            absence_end=cleaned["absence_end"],
            reason_code=cleaned.get("reason_code") or "unspecified",
        )
        packet = build_packet(
            trigger=trigger,
            substitute_id=cleaned["substitute_id"],
            lesson_outline=cleaned.get("lesson_outline_json") or [],
            seating_chart_ref=cleaned.get("seating_chart_ref") or "",
            expose_medical_iep=expose_medical,
            grace_minutes=int(cleaned.get("grace_minutes") or 30),
        )
    except SubstituteHandoverError as exc:
        return {"ok": False, "error": str(exc)}

    from apps.schoolops.micro_friction_persistence import persist_handover_packet
    from apps.schoolops.models_micro_friction import SubstituteHandoverPacketRecord

    record = persist_handover_packet(
        school_id=school_id,
        user_id=user_id,
        packet=packet,
        reason_code=cleaned.get("reason_code") or "unspecified",
        source=SubstituteHandoverPacketRecord.Source.OFFLINE,
        client_offline_id=_client_offline_id(payload),
    )

    logger.info(
        "offline_workflow.substitute_handover packet=%s school_id=%s user_id=%s",
        packet.packet_id,
        school_id,
        user_id,
        extra={"scope": "offline_workflow.substitute_handover"},
    )
    body_obj = {
        "workflow": WORKFLOW_SUBSTITUTE_HANDOVER,
        "packet_id": packet.packet_id,
        "valid_until": packet.valid_until.isoformat(),
        "tenant_id_hash": packet.tenant_id_hash,
        "teacher_id_hash": packet.teacher_id_hash,
        "substitute_id_hash": packet.substitute_id_hash,
        "medical_iep_gated": packet.medical_iep_gated,
        "periods": len(packet.lesson_outline),
    }
    note_result = _persist_workflow_note(
        school_id,
        user_id,
        payload,
        title="substitute handover (offline)",
        body_obj=body_obj,
    )
    if not note_result.get("ok"):
        return note_result
    return {
        **note_result,
        "workflow_applied": WORKFLOW_SUBSTITUTE_HANDOVER,
        "packet_id": packet.packet_id,
        "handover_record_id": record.pk,
    }


def _apply_lost_belongings_mint_capture(
    school_id: int,
    user_id: int,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    from apps.schoolops.forms_lost_belongings import MintTagForm
    from apps.schoolops.lost_belongings_qr import LostBelongingsError, mint_tag

    form = MintTagForm(data=fields)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    cleaned = form.cleaned_data
    try:
        tag = mint_tag(
            tenant_id=str(school_id),
            asset_id=cleaned["asset_id"],
            label_hint=cleaned["label_hint"],
        )
    except LostBelongingsError as exc:
        return {"ok": False, "error": str(exc)}

    from apps.schoolops.micro_friction_persistence import persist_lost_belongings_tag

    tag_record = persist_lost_belongings_tag(
        school_id=school_id,
        user_id=user_id,
        tag=tag,
        asset_id=cleaned["asset_id"],
        source="offline",
        client_offline_id=_client_offline_id(payload),
    )

    logger.info(
        "offline_workflow.lost_belongings_mint asset=%s school_id=%s",
        tag.asset_id,
        school_id,
        extra={"scope": "offline_workflow.lost_belongings_mint"},
    )
    body_obj = {
        "workflow": WORKFLOW_LOST_BELONGINGS_MINT,
        "asset_id": tag.asset_id,
        "short_code": tag.short_code,
        "label_hint": tag.label_hint,
        "tenant_id_hash": tag.tenant_id_hash,
    }
    note_result = _persist_workflow_note(
        school_id,
        user_id,
        payload,
        title="lost belongings mint (offline)",
        body_obj=body_obj,
    )
    if not note_result.get("ok"):
        return note_result
    return {
        **note_result,
        "workflow_applied": WORKFLOW_LOST_BELONGINGS_MINT,
        "short_code": tag.short_code,
        "tag_record_id": tag_record.pk,
    }


def _apply_lost_belongings_recover_capture(
    school_id: int,
    user_id: int,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    from apps.schoolops.forms_lost_belongings import StaffRecoveryForm
    from apps.schoolops.lost_belongings_qr import LostBelongingsError, record_staff_recovery
    from apps.schoolops.micro_friction_persistence import (
        lookup_tag_by_short_code,
        persist_custody_event,
        tag_record_to_asset_tag,
    )

    form = StaffRecoveryForm(data=fields)
    if not form.is_valid():
        return {"ok": False, "error": "validation", "details": dict(form.errors)}

    cleaned = form.cleaned_data
    tag_record = lookup_tag_by_short_code(
        school_id=school_id,
        short_code=cleaned["short_code"],
    )
    if tag_record is None:
        return {"ok": False, "error": "tag_not_found"}
    tag = tag_record_to_asset_tag(tag_record)
    try:
        event = record_staff_recovery(
            tag=tag,
            staff_id=cleaned["staff_id"],
            notes=cleaned.get("notes") or "",
        )
        persist_custody_event(
            school_id=school_id,
            tag_record=tag_record,
            event=event,
            staff_id=cleaned["staff_id"],
            client_offline_id=_client_offline_id(payload),
        )
    except LostBelongingsError as exc:
        return {"ok": False, "error": str(exc)}

    body_obj = {
        "workflow": WORKFLOW_LOST_BELONGINGS_RECOVER,
        "event_id": event.event_id,
        "asset_id": tag.asset_id,
        "short_code": tag.short_code,
    }
    note_result = _persist_workflow_note(
        school_id,
        user_id,
        payload,
        title="lost belongings recovery (offline)",
        body_obj=body_obj,
    )
    if not note_result.get("ok"):
        return note_result
    return {
        **note_result,
        "workflow_applied": WORKFLOW_LOST_BELONGINGS_RECOVER,
        "event_id": event.event_id,
    }


__all__ = [
    "WORKFLOW_LOST_BELONGINGS_MINT",
    "WORKFLOW_LOST_BELONGINGS_RECOVER",
    "WORKFLOW_SUBSTITUTE_HANDOVER",
    "parse_field_capture_body",
    "try_apply_field_capture_workflow",
]
