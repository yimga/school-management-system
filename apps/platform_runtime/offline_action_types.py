"""Canonical offline action types for SODP (batch 1406).

Clients queue typed intents only — never raw SMTP or free-form SEND_EMAIL.
Server validates ``action_type`` against this registry before apply.
"""

from __future__ import annotations

import re
from typing import Any

from django.db import models


class OfflineActionType(models.TextChoices):
    ATTENDANCE_MARK = "attendance.mark", "Attendance mark"
    GRADE_SUBMIT = "grade.submit", "Grade submit"
    STUDENT_NOTE = "student.note", "Student note"
    PAYMENT_PROOF = "payment.proof_upload", "Payment proof upload"
    SUPPORT_TICKET = "support.ticket", "Support ticket"
    NOTIFY_PARENT = "notify.parent", "Notify parent"
    NOTIFY_STAFF = "notify.staff", "Notify staff"
    PROVISIONAL_SIGNUP = "provision.signup", "Provisional signup"


NOTIFY_PREFIX = "notify."

# Legacy OfflineAction.ActionType values mapped to dotted SODP types.
LEGACY_TO_SODP: dict[str, str] = {
    "attendance": OfflineActionType.ATTENDANCE_MARK,
    "grading": OfflineActionType.GRADE_SUBMIT,
    "payment_receipt": OfflineActionType.PAYMENT_PROOF,
    "notes_report": OfflineActionType.STUDENT_NOTE,
}

SODP_TO_LEGACY: dict[str, str] = {v: k for k, v in LEGACY_TO_SODP.items()}

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password",
        "host_password",
        "send_email",
        "SEND_EMAIL",
        "to_email",
        "raw_to",
    }
)

_NOTIFY_TEMPLATE_KEYS = frozenset(
    {
        "low_meal_balance",
        "exam_readiness",
        "fee_reminder",
        "transport_delay",
        "wellbeing_checkin",
    }
)


def is_notify_action(action_type: str) -> bool:
    return (action_type or "").startswith(NOTIFY_PREFIX)


def normalize_action_type(action_type: str) -> str:
    """Map legacy queue types to dotted SODP types when applicable."""
    raw = (action_type or "").strip()
    if raw in LEGACY_TO_SODP:
        return LEGACY_TO_SODP[raw]
    return raw


def validate_offline_payload(action_type: str, payload: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty = valid)."""
    errors: list[str] = []
    at = normalize_action_type(action_type)
    if at not in OfflineActionType.values:
        errors.append(f"unknown action_type: {at}")
    if not isinstance(payload, dict):
        return errors + ["payload must be an object"]

    lowered_keys = {str(k).lower() for k in payload.keys()}
    forbidden = sorted(k for k in FORBIDDEN_PAYLOAD_KEYS if k.lower() in lowered_keys)
    if forbidden:
        errors.append(f"forbidden payload keys: {', '.join(forbidden)}")

    if is_notify_action(at):
        template_key = (payload.get("template_key") or "").strip()
        if not template_key:
            errors.append("notify.* requires template_key")
        elif template_key not in _NOTIFY_TEMPLATE_KEYS:
            errors.append(f"unsupported template_key: {template_key}")
        if not (payload.get("recipient_user_id") or payload.get("recipient_id")):
            errors.append("notify.* requires recipient_user_id")

    if at == OfflineActionType.PROVISIONAL_SIGNUP:
        device_id = (payload.get("device_id") or "").strip()
        if not device_id or not re.match(r"^[a-zA-Z0-9._-]{8,128}$", device_id):
            errors.append("provision.signup requires device_id (8-128 alnum)")

    return errors


__all__ = [
    "FORBIDDEN_PAYLOAD_KEYS",
    "LEGACY_TO_SODP",
    "NOTIFY_PREFIX",
    "OfflineActionType",
    "SODP_TO_LEGACY",
    "is_notify_action",
    "normalize_action_type",
    "validate_offline_payload",
]
