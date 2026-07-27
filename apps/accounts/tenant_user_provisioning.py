"""Provision a tenant user directly with an admin-set TEMPORARY password.

The counterpart to the token-invite path (``tenant_staff_invites``): instead of
emailing a link for the invitee to set their own password, an admin creates the
account NOW with a temporary password and hands it over (in person, on a printed
slip, over the phone). The account is flagged so ``OnboardingEnforcementMiddleware``
forces the user to change the password AND complete their profile on first login.

Roles are derived from ``User.Role`` (no hardcoded role list) minus a small deny
set — students have their own create flow, and platform-level roles are not
tenant-provisionable here.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

User = get_user_model()

# Not directly provisionable from the tenant identity surface (roles referenced
# from User.Role — the SOT — never hardcoded strings):
#   SUPERADMIN         — platform operator, not a tenant account
#   STUDENT            — provisioned via the student-create flow (+ guardian link)
#   EMPLOYER           — external careers/partner actor
#   VIRTUAL_ASSISTANT  — automation principal, not a human login
_NON_PROVISIONABLE = frozenset(
    {
        User.Role.SUPERADMIN,
        User.Role.STUDENT,
        User.Role.EMPLOYER,
        User.Role.VIRTUAL_ASSISTANT,
    }
)


class ProvisioningError(ValueError):
    """Raised for a bad provisioning request (surfaced to the admin as a message)."""


def provisionable_role_choices():
    """(value, label) pairs an admin may directly provision with a temp password."""
    return [(c[0], c[1]) for c in User.Role.choices if c[0] not in _NON_PROVISIONABLE]


def provision_tenant_user_with_temp_password(
    *,
    school,
    email,
    role,
    temp_password,
    invited_by=None,
    username=None,
    first_name="",
    last_name="",
):
    """Create (and school-link) a tenant user with an admin-set temporary password.

    Returns ``(user, created)``. Raises ``ProvisioningError`` on a bad request or
    when an account that already has a usable password exists (never silently
    clobbers an active user's password).
    """
    from apps.schools.models import SchoolMembership

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ProvisioningError("A valid email address is required.")
    role = (role or "").strip().upper()
    valid_roles = {c[0] for c in User.Role.choices}
    if role not in valid_roles or role in _NON_PROVISIONABLE:
        raise ProvisioningError(f"Role {role!r} cannot be provisioned here.")
    temp_password = (temp_password or "").strip()
    if len(temp_password) < 8:
        raise ProvisioningError("The temporary password must be at least 8 characters.")
    if school is None:
        raise ProvisioningError("A school is required to provision a tenant user.")

    uname = (username or email).strip()

    with transaction.atomic():
        existing = (
            User.objects.filter(Q(username__iexact=uname) | Q(email__iexact=email))
            .distinct()
            .first()
        )
        if existing is not None and existing.has_usable_password():
            raise ProvisioningError(
                f"An account for {email} already exists. Use the roster to manage it."
            )

        user = existing or User(username=uname, email=email)
        created = existing is None
        user.email = email
        if created:
            user.role = role
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        user.is_active = True
        # Every temp-password account must complete onboarding before use.
        user.requires_password_change = True
        user.profile_setup_completed = False
        user.set_password(temp_password)
        user.save()

        has_primary = SchoolMembership.objects.filter(  # tenant-isolation-allow: user-scoped primary-membership check
            user=user, is_primary=True
        ).exists()
        SchoolMembership.objects.get_or_create(
            user=user,
            school=school,
            defaults={"role": role, "is_primary": not has_primary},
        )

    return user, created
