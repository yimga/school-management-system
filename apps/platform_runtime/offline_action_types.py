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
    HOMEWORK_SUBMIT = "homework.submit", "Homework submit"
    PAYMENT_PROOF = "payment.proof_upload", "Payment proof upload"
    MIGRATION_BUNDLE_UPLOAD = "migration.bundle_upload", "Migration Cloud upload"
    SUPPORT_TICKET = "support.ticket", "Support ticket"
    NOTIFY_PARENT = "notify.parent", "Notify parent"
    NOTIFY_STAFF = "notify.staff", "Notify staff"
    PROVISIONAL_SIGNUP = "provision.signup", "Provisional signup"
    IAM_REQUEST_ACCESS = "iam.request_access", "IAM request access (server-validated)"
    REPORT_BATCH_DISTRIBUTE = "report_batch.distribute", "Report card batch distribute"


NOTIFY_PREFIX = "notify."

# Legacy OfflineAction.ActionType values mapped to dotted SODP types.
LEGACY_TO_SODP: dict[str, str] = {
    "attendance": OfflineActionType.ATTENDANCE_MARK,
    "grading": OfflineActionType.GRADE_SUBMIT,
    "payment_receipt": OfflineActionType.PAYMENT_PROOF,
    "notes_report": OfflineActionType.STUDENT_NOTE,
    "homework_submission": OfflineActionType.HOMEWORK_SUBMIT,
    "support_ticket": OfflineActionType.SUPPORT_TICKET,
    "migration_cloud_upload": OfflineActionType.MIGRATION_BUNDLE_UPLOAD,
}

SODP_TO_LEGACY: dict[str, str] = {v: k for k, v in LEGACY_TO_SODP.items()}
SODP_TO_LEGACY[OfflineActionType.NOTIFY_PARENT] = OfflineActionType.NOTIFY_PARENT
SODP_TO_LEGACY[OfflineActionType.NOTIFY_STAFF] = OfflineActionType.NOTIFY_STAFF
SODP_TO_LEGACY[OfflineActionType.PROVISIONAL_SIGNUP] = OfflineActionType.PROVISIONAL_SIGNUP

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

    if at == OfflineActionType.SUPPORT_TICKET:
        if not str(payload.get("subject") or "").strip():
            errors.append("support.ticket requires subject")
        if not str(payload.get("message") or payload.get("body") or "").strip():
            errors.append("support.ticket requires message")

    if at == OfflineActionType.REPORT_BATCH_DISTRIBUTE:
        # A distribution is bound to a term of an academic year; the group ref
        # (classroom/specialty) is optional (absent = whole year).
        if payload.get("academic_year_id") in (None, ""):
            errors.append("report_batch.distribute requires academic_year_id")
        if payload.get("term_id") in (None, ""):
            errors.append("report_batch.distribute requires term_id")

    if at == OfflineActionType.HOMEWORK_SUBMIT:
        # Canonical path carries assignment_id (academics.LMSSubmission); the legacy
        # kernel path carries homework_id (School.settings edge store). Either is valid.
        has_assignment = str(payload.get("assignment_id") or "").strip()
        has_homework = str(payload.get("homework_id") or "").strip()
        if not has_assignment and not has_homework:
            errors.append("homework.submit requires assignment_id (or legacy homework_id)")
        student_id = payload.get("student_id")
        if student_id in (None, ""):
            errors.append("homework.submit requires student_id")

    if at == OfflineActionType.MIGRATION_BUNDLE_UPLOAD:
        filenames = payload.get("filenames")
        if not isinstance(filenames, list) or not filenames:
            errors.append("migration.bundle_upload requires filenames[]")
        # Forbid embedding multi-MB base64 in the JSON SODP payload.
        for banned in ("file_base64", "files_base64", "content_base64", "blob_base64"):
            if banned in payload:
                errors.append(f"migration.bundle_upload forbids {banned} in JSON payload")
        client_id = str(payload.get("client_offline_id") or "").strip()
        if not client_id:
            errors.append("migration.bundle_upload requires client_offline_id")

    if at == OfflineActionType.IAM_REQUEST_ACCESS:
        code = str(payload.get("permission_code") or "").strip()
        if not code:
            errors.append("iam.request_access requires permission_code")

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
