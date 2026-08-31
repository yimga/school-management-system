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

import math

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

# Re-exported so the admin provisioning surface can offer a minted credential as
# the field default instead of leaving entropy to whatever a human types.
from apps.accounts.credential_reset import generate_temp_password

User = get_user_model()

__all__ = [
    "ProvisioningError",
    "TEMP_PASSWORD_MIN_BITS",
    "TEMP_PASSWORD_MIN_DISTINCT",
    "TEMP_PASSWORD_MIN_LENGTH",
    "generate_temp_password",
    "is_provisionable_role",
    "provision_tenant_user_with_temp_password",
    "provisionable_role_choices",
    "temp_password_entropy_bits",
    "validate_temp_password",
]

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


# --------------------------------------------------------------------------- #
# Temporary-credential strength floor
# --------------------------------------------------------------------------- #
# The audited property is that a provisioned account is created with a HIGH-ENTROPY
# temporary credential. ``credential_reset.generate_temp_password`` mints 14 chars
# over a 54-symbol unambiguous alphabet = 80.57 bits and is the recommended source
# (re-exported here so the admin surface can offer it as the field default).
#
# This gate is the floor for the OTHER case — a password an admin typed into the
# provisioning form. Until now the only check was ``len >= 8``, so the literal
# string "password" (37.6 bits, top of every wordlist) provisioned an account.
#
# Django's own AUTH_PASSWORD_VALIDATORS are deliberately NOT used here: their
# CommonPasswordValidator rejects strings this repo's existing provisioning tests
# depend on, and the audited property is entropy, not list membership. Bits are
# measured as ``len * log2(pool)`` where ``pool`` covers the character classes
# actually present — the search space an attacker who knows the shape must cover.
# ``TEMP_PASSWORD_MIN_DISTINCT`` is the companion guard, because a pool estimate
# over-credits a repeated string ("aaaaaaaaaaaa" alone scores 56 bits).
TEMP_PASSWORD_MIN_LENGTH = 8  # magic-number-allow: temp-credential-length-floor
TEMP_PASSWORD_MIN_BITS = 40.0  # magic-number-allow: temp-credential-entropy-floor
TEMP_PASSWORD_MIN_DISTINCT = 5  # magic-number-allow: temp-credential-distinct-floor


def temp_password_entropy_bits(password) -> float:
    """Search-space entropy of ``password`` in bits (``len * log2(class pool)``)."""
    password = password or ""
    if not password:
        return 0.0
    pool = 0
    if any(c.islower() for c in password):
        pool += 26  # magic-number-allow: lowercase-latin-class-size
    if any(c.isupper() for c in password):
        pool += 26  # magic-number-allow: uppercase-latin-class-size
    if any(c.isdigit() for c in password):
        pool += 10  # magic-number-allow: decimal-digit-class-size
    if any(not c.isalnum() for c in password):
        pool += 32  # magic-number-allow: printable-symbol-class-size
    if pool <= 1:
        return 0.0
    return len(password) * math.log2(pool)


def validate_temp_password(temp_password) -> str:
    """Return the stripped credential, or raise ``ProvisioningError`` when it is weak.

    Three independent floors: length, distinct characters, and measured entropy.
    A caller with no password of its own should mint one with
    :func:`generate_temp_password` rather than satisfying this by hand.
    """
    temp_password = (temp_password or "").strip()
    if len(temp_password) < TEMP_PASSWORD_MIN_LENGTH:
        raise ProvisioningError("The temporary password must be at least 8 characters.")
    if len(set(temp_password)) < TEMP_PASSWORD_MIN_DISTINCT:
        raise ProvisioningError(
            "The temporary password reuses too few characters — it must contain at "
            f"least {TEMP_PASSWORD_MIN_DISTINCT} different ones."
        )
    bits = temp_password_entropy_bits(temp_password)
    if bits < TEMP_PASSWORD_MIN_BITS:
        raise ProvisioningError(
            "The temporary password is too easy to guess "
            f"({bits:.0f} bits of entropy; at least {TEMP_PASSWORD_MIN_BITS:.0f} are "
            "required). Mix upper and lower case, digits and symbols — or use a "
            "generated one."
        )
    return temp_password


def provisionable_role_choices():
    """(value, label) pairs an admin may directly provision with a temp password."""
    return [(c[0], c[1]) for c in User.Role.choices if c[0] not in _NON_PROVISIONABLE]


def is_provisionable_role(role) -> bool:
    """True when ``role`` is a real, tenant-provisionable role (not the deny set)."""
    role = (role or "").strip().upper()
    return role in {c[0] for c in User.Role.choices} and role not in _NON_PROVISIONABLE


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
    temp_password = validate_temp_password(temp_password)
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
