"""Apply offline IAM intents server-side (never trust client grants)."""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.accounts.rebac import check_permission_token

logger = logging.getLogger(__name__)

FORBIDDEN_INTENT_PERMISSIONS = frozenset(
    {
        "settings.manage",
        "users.manage",
        "roles.manage",
        "security.manage",
        "platform.admin",
    },
)


def apply_offline_access_intent(intent) -> tuple[bool, str]:
    """
    Process a queued ``OfflineAccessIntent``. Returns (applied, note).
    Does not grant permissions — records request for operator review.
    """
    from apps.accounts.models_rebac import OfflineAccessIntent

    if intent.status != OfflineAccessIntent.Status.QUEUED:
        return False, "already_processed"
    payload = intent.payload or {}
    code = (payload.get("permission_code") or "").strip()
    if not code:
        intent.status = OfflineAccessIntent.Status.REJECTED
        intent.server_note = "missing_permission_code"
        intent.save(update_fields=["status", "server_note", "updated_at"])
        return False, intent.server_note
    if code in FORBIDDEN_INTENT_PERMISSIONS:
        intent.status = OfflineAccessIntent.Status.REJECTED
        intent.server_note = "forbidden_capability"
        intent.applied_at = timezone.now()
        intent.save(
            update_fields=["status", "server_note", "applied_at", "updated_at"],
        )
        return True, intent.server_note
    user = intent.user
    school = intent.school
    if check_permission_token(user, code, school=school):
        intent.status = OfflineAccessIntent.Status.APPLIED
        intent.server_note = "already_has_capability"
    else:
        intent.status = OfflineAccessIntent.Status.APPLIED
        intent.server_note = "request_logged_for_review"
    intent.applied_at = timezone.now()
    intent.save(update_fields=["status", "server_note", "applied_at", "updated_at"])
    logger.info(
        "offline_iam_intent_applied intent_id=%s user_id=%s code=%s note=%s",
        intent.pk,
        user.pk,
        code,
        intent.server_note,
    )
    return True, intent.server_note


def enqueue_request_access(*, user, school, permission_code: str, reason: str = "", idempotency_key: str = ""):
    from apps.accounts.models_rebac import OfflineAccessIntent

    return OfflineAccessIntent.objects.create(
        user=user,
        school=school,
        intent_type=OfflineAccessIntent.IntentType.REQUEST_ACCESS,
        payload={
            "permission_code": (permission_code or "").strip(),
            "reason": (reason or "")[:500],
        },
        idempotency_key=(idempotency_key or "")[:128],
    )
