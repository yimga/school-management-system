"""Self-service school join codes — the Google Classroom pattern.

An admin generates a short code (optionally domain-restricted, use-capped, and/or
time-boxed); a prospective parent/teacher/staff member enters it on the school's
join page and registers themselves. Redemption creates the ``User`` + a
``SchoolMembership`` with the code's preset role. Self-join users set their own
password and name, so they are NOT forced through the temp-password onboarding.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

User = get_user_model()

# Human-typeable alphabet: no ambiguous 0/O/1/I/L.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 8


class JoinCodeError(ValueError):
    """Bad join-code request (surfaced to the user as a message)."""


def _generate_code_string() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


def generate_join_code(
    *,
    school,
    role,
    created_by=None,
    label="",
    domain_allowlist="",
    max_uses=None,
    expires_at=None,
):
    """Create and return a new ``SchoolJoinCode`` with a unique code string."""
    from apps.accounts.models import SchoolJoinCode
    from apps.accounts.tenant_user_provisioning import is_provisionable_role

    role = (role or "").strip().upper()
    if not is_provisionable_role(role):
        raise JoinCodeError(f"Role {role!r} cannot be used for a join code.")
    if school is None:
        raise JoinCodeError("A school is required to create a join code.")

    for _ in range(12):
        code = _generate_code_string()
        # tenant-isolation-allow: join-code-uniqueness-is-a-global-bearer-credential-collision-check
        if not SchoolJoinCode.objects.filter(code=code).exists():
            break
    else:  # pragma: no cover - astronomically unlikely
        raise JoinCodeError("Could not allocate a unique code; please try again.")

    return SchoolJoinCode.objects.create(
        school=school,
        code=code,
        role=role,
        created_by=created_by,
        label=(label or "").strip()[:120],
        domain_allowlist=(domain_allowlist or "").strip()[:255],
        max_uses=max_uses,
        expires_at=expires_at,
    )


def resolve_join_code(code, *, school=None):
    """Return the ``SchoolJoinCode`` for ``code`` (optionally scoped to a school),
    or None. Does not check usability — callers surface the specific reason."""
    from apps.accounts.models import SchoolJoinCode

    code = (code or "").strip().upper()
    if not code:
        return None
    # tenant-isolation-allow: join-code-resolved-by-bearer-credential-then-optionally-school-narrowed
    qs = SchoolJoinCode.objects.filter(code=code)
    if school is not None:
        qs = qs.filter(school=school)
    return qs.first()


def redeem_join_code(*, code, email, password, first_name="", last_name="", school=None):
    """Redeem ``code``: create/activate the ``User`` + school membership with the
    code's role and increment its use count. Returns the user. Raises
    ``JoinCodeError`` for any invalid/exhausted/expired/domain-blocked case."""
    from apps.accounts.models import SchoolJoinCode
    from apps.schools.models import SchoolMembership

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise JoinCodeError("A valid email address is required.")
    if len((password or "").strip()) < 8:
        raise JoinCodeError("Password must be at least 8 characters.")

    with transaction.atomic():
        join_code = (
            SchoolJoinCode.objects.select_for_update()
            .filter(code=(code or "").strip().upper())
            .first()
        )
        if join_code is None or (school is not None and join_code.school_id != school.id):
            raise JoinCodeError("That join code is not valid.")
        if not join_code.is_usable:
            raise JoinCodeError("That join code is no longer active.")
        if not join_code.domain_allowed(email):
            raise JoinCodeError("Your email domain is not permitted for this code.")

        existing = (
            User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email))
            .distinct()
            .first()
        )
        if existing is not None and existing.has_usable_password():
            raise JoinCodeError(
                "An account with this email already exists — please sign in instead."
            )

        user = existing or User(username=email, email=email, role=join_code.role)
        if first_name:
            user.first_name = first_name.strip()
        if last_name:
            user.last_name = last_name.strip()
        user.is_active = True
        # Self-join: user chose their own password + name — no forced onboarding.
        user.requires_password_change = False
        user.profile_setup_completed = True
        user.set_password(password)
        user.save()

        has_primary = SchoolMembership.objects.filter(  # tenant-isolation-allow: user-scoped primary-membership check
            user=user, is_primary=True
        ).exists()
        SchoolMembership.objects.get_or_create(
            user=user,
            school=join_code.school,
            defaults={"role": join_code.role, "is_primary": not has_primary},
        )
        SchoolJoinCode.objects.filter(pk=join_code.pk).update(
            uses_count=join_code.uses_count + 1
        )

    return user
