"""password_rotation wizard → rotate the ACTOR's own account password.

Distinct from encryption-key rotation (``apps.accounts.legacy_hashes.key_rotation``).
Validates strength via Django's ``AUTH_PASSWORD_VALIDATORS``, sets the new
password, clears any forced-change flag, revokes the actor's other sessions
(best-effort), and records a security-audit event.
"""
from __future__ import annotations

import logging

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger(__name__)


def perform_password_rotation(*, actor_user_id, payload, school=None) -> dict:
    """Rotate the password of the user identified by ``actor_user_id``.

    Returns a structured result dict. The call site (wizard ``confirm`` step)
    passes ``actor_user_id`` and ``payload``; ``school`` is optional and used
    only for audit/session-scope context.
    """
    from apps.accounts.models import User

    data = payload or {}
    new_password = data.get("new_password") or data.get("password") or ""
    confirm = data.get("confirm_password")
    if not actor_user_id or not new_password:
        return {"ok": False, "error": "missing_inputs"}
    if confirm is not None and confirm != new_password:
        return {"ok": False, "error": "password_mismatch"}

    try:
        user = User.objects.get(pk=actor_user_id)
    except User.DoesNotExist:
        logger.warning("perform_password_rotation: actor %s not found", actor_user_id)
        return {"ok": False, "error": "actor_not_found"}

    try:
        password_validation.validate_password(new_password, user=user)
    except ValidationError as exc:
        return {"ok": False, "error": "weak_password", "messages": list(exc.messages)}

    user.set_password(new_password)
    update_fields = ["password"]
    for field, value in (
        ("requires_password_change", False),
        ("password_changed_at", timezone.now()),
    ):
        if hasattr(user, field):
            setattr(user, field, value)
            update_fields.append(field)
    user.save(update_fields=update_fields)

    revoked = _revoke_other_sessions(user=user, school=school)
    _audit_rotation(user=user, school=school)
    logger.info(
        "perform_password_rotation user=%s revoked_sessions=%s", user.pk, revoked
    )
    return {"ok": True, "user_id": user.pk, "revoked_sessions": revoked}


def _revoke_other_sessions(*, user, school) -> int:
    """Best-effort revocation of the user's other sessions after a password change."""
    try:
        from apps.lifecycle.purge_operations import revoke_all_sessions_for_school

        school_id = (
            str(school.pk)
            if school is not None and getattr(school, "pk", None)
            else None
        )
        return int(
            revoke_all_sessions_for_school(school_id=school_id, user_ids=[user.pk]) or 0
        )
    except Exception as exc:  # noqa: BLE001 — session revocation is best-effort hardening
        logger.debug("password rotation session revoke skipped: %s", exc)
        return 0


def _audit_rotation(*, user, school) -> None:
    """Best-effort security-audit event for the password change."""
    try:
        from apps.accounts.models import SecurityAuditLog
        from apps.accounts.security_audit import log_security_event

        log_security_event(
            user=user,
            event_type=SecurityAuditLog.EventType.PWD_RESET,
            request=None,
            school=school,
            is_suspicious=False,
            initiator="self",
        )
    except Exception as exc:  # noqa: BLE001 — audit is best-effort
        logger.debug("password rotation audit skipped: %s", exc)
