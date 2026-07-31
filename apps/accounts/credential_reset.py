"""Tenant-admin credential recovery — reset another member's password / MFA.

A school delegate holding the ``identity.reset_credentials`` capability (owners
and the tenant-admin roles by default; grantable to ANY role via the RBAC
dashboard) can recover a locked-out member: issue a one-time temporary password
(forcing a change on next login) or clear the member's MFA devices so they
re-enroll. This mirrors the operator-only ``reset_user_mfa`` management command
and the temp-password provisioning pattern, but is reachable in-app and strictly
school-scoped.

Security invariants (enforced by :func:`can_reset_target`):
  * The actor must hold the capability on *this* school and not be suspended.
  * The target must be a member of the SAME school (cross-tenant isolation).
  * Only an owner (or platform superuser) may reset an ACTIVE owner's
    credentials — a lesser admin must not seize the tenant by resetting the
    person who owns it.
  * A platform superuser target may only be reset by another superuser.

The temporary password is returned to the caller to hand over ONCE; it is never
logged. Only PK-level structured audit lines + a ``SecurityAuditLog`` row are
written (no usernames/emails — passes the pii-logging-smell gate).
"""

from __future__ import annotations

import logging
import secrets

from django.db import transaction

logger = logging.getLogger("security.account_recovery")

#: Capability code, grantable to roles via the RBAC dashboard. Seeded to the
#: tenant-admin roles by migration ``0057``; the ``require_permission`` gate also
#: admits the tenant-admin tier + platform superuser by default.
RESET_CREDENTIALS_CODE = "identity.reset_credentials"

# Unambiguous alphabet — no 0/O/1/l/I so a hand-transcribed temp password is not
# misread. 14 chars over this 54-char set is ~80 bits of entropy.
_TEMP_PW_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
_TEMP_PW_LENGTH = 14


def generate_temp_password(length: int = _TEMP_PW_LENGTH) -> str:
    """Return a cryptographically-random, transcription-friendly temp password."""
    return "".join(secrets.choice(_TEMP_PW_ALPHABET) for _ in range(length))


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
def _membership(user, school):
    from apps.schools.models import SchoolMembership

    return SchoolMembership.objects.filter(
        user_id=getattr(user, "pk", None), school_id=getattr(school, "pk", None)
    ).first()


def _is_active_owner(user, school) -> bool:
    from apps.schools.models import SchoolMembership

    return SchoolMembership.objects.filter(
        school_id=getattr(school, "pk", None),
        user_id=getattr(user, "pk", None),
        is_school_owner=True,
        suspended_at__isnull=True,
    ).exists()


def can_reset_credentials(actor, school) -> bool:
    """Whether ``actor`` holds the credential-reset capability on ``school``.

    Superuser always; otherwise a non-suspended member who satisfies
    ``require_permission("identity.reset_credentials")`` (the assignable code OR
    the tenant-admin tier by default).
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    if getattr(actor, "is_superuser", False):
        return True
    from apps.accounts.decorators import user_has_permission
    from apps.accounts.tenant_identity import user_has_school_membership

    if not user_has_school_membership(actor, school):
        return False
    membership = _membership(actor, school)
    if membership is not None and membership.suspended_at is not None:
        # A suspended member keeps their row but holds no authority.
        return False
    return user_has_permission(actor, school, (RESET_CREDENTIALS_CODE,))


def can_reset_target(actor, target, school) -> bool:
    """Full guard: capability + same-school scope + owner/superuser protection."""
    if target is None or not can_reset_credentials(actor, school):
        return False
    from apps.accounts.tenant_identity import user_has_school_membership

    if not user_has_school_membership(target, school):
        # Cross-tenant / non-member — never resettable from this school.
        return False
    if getattr(target, "is_superuser", False) and not getattr(
        actor, "is_superuser", False
    ):
        # A platform operator identity is out of a tenant admin's reach.
        return False
    if _is_active_owner(target, school):
        # Resetting an owner is authority-bearing — owner (or superuser) only.
        if getattr(actor, "is_superuser", False):
            return True
        return _is_active_owner(actor, school)
    return True


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def set_temporary_password(user) -> tuple[str, bool]:
    """Core: set a fresh temp password, force a change next login, reactivate if inactive.

    Returns ``(temp_password, was_reactivated)``. Shared by the TENANT credential
    reset (:func:`admin_reset_password`) and the OPERATOR-team reset so both offer
    the SAME email-independent recovery — the reason this exists: in a
    low-connectivity area the self-serve "forgot my password" email never reaches
    the user, so an admin hands over the returned plaintext temp password
    out-of-band and the user signs in with no internet of their own.

    An INACTIVE account is reactivated (``is_active=True``): a reset whose whole
    point is to restore sign-in must not leave the account inactive, because
    ``authenticate()`` rejects any inactive account no matter the password — the
    silent "invalid username or password" wall (the ``novijonongni`` symptom). A
    change is forced on next sign-in so the temporary secret is never durable.
    Callers are responsible for revoking the target's live sessions so the temp
    password takes effect immediately. Never logs the password.
    """
    temp = generate_temp_password()
    was_inactive = not user.is_active
    with transaction.atomic():
        user.set_password(temp)
        user.requires_password_change = True
        update_fields = ["password", "requires_password_change"]
        if was_inactive:
            user.is_active = True
            update_fields.append("is_active")
        user.save(update_fields=update_fields)
    return temp, was_inactive


def admin_reset_password(actor, target, school, *, request=None) -> str:
    """Tenant credential reset — temp password + forced change + reactivation.

    Thin school-scoped wrapper over :func:`set_temporary_password` that adds the
    tenant SecurityAuditLog line. Returns the plaintext temp password for the
    caller to hand over ONCE. The reactivation is surfaced to the admin by the
    view (not silent); ``can_reset_target`` still enforces the owner/superuser
    guards. Makes the assignable ``identity.reset_credentials`` capability usable
    by a NON-owner admin (the owner-only "Reactivate" button is otherwise out of
    reach). Supersedes the earlier "leave a deactivated-real account inactive"
    rule (see finding_never_claimed_inactive_account_lockout).
    """
    temp, _was_reactivated = set_temporary_password(target)
    _audit(actor, target, school, "password_reset", request=request)
    return temp


def admin_reset_mfa(actor, target, school, *, request=None) -> dict:
    """Clear ``target``'s MFA devices so they re-enroll on next login.

    Reuses the operator recovery core ``reset_mfa_for_user`` (TOTP + backup codes
    + passkeys + device-trust) and drops any MFA-setup deferral so the re-enroll
    is not itself deferred by a stale window. Idempotent for a never-enrolled
    user. Returns the per-type removal counts.
    """
    from apps.accounts.management.commands.reset_user_mfa import reset_mfa_for_user
    from apps.accounts.mfa_deferral import clear_mfa_setup_deferral

    counts = reset_mfa_for_user(target)
    clear_mfa_setup_deferral(target)
    _audit(actor, target, school, "mfa_reset", request=request, extra=counts)
    return counts


def _audit(actor, target, school, action: str, *, request=None, extra=None) -> None:
    """Record a credential-recovery action — PK-only, no PII."""
    try:
        from apps.accounts.models import SecurityAuditLog
        from apps.accounts.security_audit import log_security_event

        event = (
            SecurityAuditLog.EventType.PWD_RESET
            if action == "password_reset"
            else SecurityAuditLog.EventType.MFA_CHANGE
        )
        log_security_event(actor, event, request=request, school=school)
    except Exception:  # noqa: BLE001 — audit is best-effort; the action still happened
        pass
    logger.warning(
        "credential_reset.%s actor=%s target=%s school=%s counts=%s",
        action,
        getattr(actor, "pk", None),
        getattr(target, "pk", None),
        getattr(school, "pk", None),
        extra or {},
    )
