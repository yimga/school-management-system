"""Creation and delivery contract for school-scoped staff/owner invitations."""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import TenantStaffInvite, User

INVITE_LIFETIME_DAYS = 7


def normalize_invite_email(value: str) -> str:
    email = (value or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise ValueError("A valid email address is required.") from exc
    return email


def create_tenant_staff_invite(
    *,
    school,
    email: str,
    role: str = User.Role.TEACHER,
    invited_by=None,
    is_school_owner: bool = False,
) -> tuple[TenantStaffInvite, bool]:
    """Create or refresh one pending invite without producing duplicates."""
    email = normalize_invite_email(email)
    role = User.Role.ADMIN if is_school_owner else str(role or "").strip().upper()
    valid_roles = {value for value, _label in User.Role.choices}
    if role not in valid_roles:
        raise ValueError(f"Unsupported tenant role: {role!r}.")

    now = timezone.now()
    expires_at = now + timedelta(days=INVITE_LIFETIME_DAYS)
    invite = (
        TenantStaffInvite.objects.filter(
            school=school,
            email__iexact=email,
            accepted_at__isnull=True,
            expires_at__gte=now,
            is_school_owner=bool(is_school_owner),
        )
        .order_by("-created_at")
        .first()
    )
    if invite is not None:
        invite.email = email
        invite.role = role
        invite.expires_at = expires_at
        if invited_by is not None:
            invite.invited_by = invited_by
        invite.save(
            update_fields=["email", "role", "expires_at", "invited_by"]
        )
        return invite, False

    return (
        TenantStaffInvite.objects.create(
            school=school,
            email=email,
            role=role,
            is_school_owner=bool(is_school_owner),
            invited_by=invited_by,
            expires_at=expires_at,
        ),
        True,
    )


def tenant_staff_invite_accept_url(invite, *, request=None) -> str:
    path = reverse(
        "accounts:tenant_staff_invite_accept", kwargs={"token": invite.token}
    )
    if request is not None:
        return request.build_absolute_uri(path)
    from apps.schools.provision_email_urls import build_tenant_authentication_url

    return build_tenant_authentication_url(invite.school, path)


def send_tenant_staff_invite(invite, *, accept_url: str = "") -> bool:
    """Deliver an invite through the transactional-email reliability layer."""
    from apps.schoolops.email_delivery import send_transactional

    school_name = getattr(invite.school, "name", "") or _("your school")
    accept_url = accept_url or tenant_staff_invite_accept_url(invite)
    if invite.is_school_owner:
        subject = _("You're invited to administer %(school)s on RunMyCampus") % {
            "school": school_name
        }
        role_label = _("school owner")
        next_steps = _(
            "Use the link to set your password. You must then enroll MFA before "
            "you can enter the school workspace."
        )
    else:
        subject = _("You're invited to join %(school)s on RunMyCampus") % {
            "school": school_name
        }
        role_label = invite.role
        next_steps = _("Use the link to create your account.")
    result = send_transactional(
        subject=subject,
        body=_(
            "You have been invited to join %(school)s as %(role)s.\n\n"
            "%(next_steps)s\n\n"
            "Accept your invitation (valid %(days)d days):\n%(url)s\n"
        )
        % {
            "school": school_name,
            "role": role_label,
            "next_steps": next_steps,
            "days": INVITE_LIFETIME_DAYS,
            "url": accept_url,
        },
        to=[invite.email],
        priority="transactional",
        school=invite.school,
        allow_suppressed=True,
        idempotency_key=f"staff_invite:{invite.token}",
    )
    return bool(result.get("ok") or result.get("queued"))


__all__ = [
    "INVITE_LIFETIME_DAYS",
    "create_tenant_staff_invite",
    "normalize_invite_email",
    "send_tenant_staff_invite",
    "tenant_staff_invite_accept_url",
]
