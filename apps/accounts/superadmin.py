"""Who owns the keys to the kingdom, and why.

The platform has two distinct god-mode signals and they were never resolved in
one place:

* ``User.is_superuser`` — Django's own flag. Every resolver in the codebase
  already fast-allows on it (``has_feature_permission``, ``can_access_module``,
  ``has_school_permission``, ``rebac.check``, the DRF classes). That half worked.
* ``role == "SUPERADMIN"`` — the platform's OWN top role. This one only ever
  short-circuited at the MODULE layer (``can_access_module``). At the
  permission-CODE layer a SUPERADMIN was resolved like any other user: through
  whatever ``AccessRole.permissions`` rows happened to be seeded. So a
  SUPERADMIN who was not also a Django superuser was denied any code the seed
  had not explicitly granted them — and the seed drifts every time a migration
  adds a code (0019, 0048, 0049, 0050, 0057 each hand-listed SUPERADMIN, and
  ``iam.request_access`` was missed).

Worse, ``signals.ROLE_TEMPLATES`` mapped ``SUPERADMIN -> ["ADMIN"]``, so the
platform's top role was materialised as the ADMIN access role, which does not
carry ``settings.feature_control``, ``api_center.manage``, ``accounting.*``,
``stock.*``, ``discipline.manage``, ``exam_registration.manage``,
``cahier.verify`` or the ``portal.documents/forums/video`` codes.

This module is the single answer to "does this account hold everything?", and
``has_feature_permission`` now consults it BEFORE resolving any grant row. That
makes coverage structural rather than seeded: a permission code added tomorrow
is held by a superadmin the moment it exists, with no migration to remember.

SCOPE — deliberately bounded, and this is a security boundary, not an oversight:

* God-mode here is CAPABILITY ("may I reach this surface / perform this action"),
  which is what "you do not have enough permissions" actually means. It does not
  silently widen the tenant-PII object gates in ``permissions.py``, which strip
  control-plane roles on purpose (``_strip_control_plane_roles``) so an operator
  reads tenant student data through audited impersonation rather than by
  accident. That isolation is enforced by
  ``TenantHostControlPlaneIsolationMiddleware``, not by withholding capability.
* Only the GLOBAL ``SUPERADMIN`` access role (``school IS NULL`` — the platform
  template) confers god-mode. A tenant can mint its own catalog row with the
  code ``SUPERADMIN`` (the unique constraint is per-school), and honouring that
  would let any tenant admin who can create a role escalate to platform god-mode.
  A school-scoped row grants exactly the permissions attached to it, nothing more.
"""

from __future__ import annotations

from typing import Any

#: The platform's top role code. Kept as one constant so the string never gets
#: retyped into a comparison that then drifts.
SUPERADMIN_ROLE_CODE = "SUPERADMIN"

#: Why a user resolved as a superadmin — surfaced on the profile so the grant is
#: legible instead of magic, and used by the RBAC console to explain the badge.
REASON_DJANGO_SUPERUSER = "django-superuser"
REASON_PRIMARY_ROLE = "primary-role"
REASON_ASSIGNED_ROLE = "assigned-role"


def _role_code(raw: Any) -> str:
    """Normalize ``User.role`` (TextChoices member, str, or None) for comparison."""
    if raw is None:
        return ""
    value = getattr(raw, "value", None)
    return str(value if value is not None else raw).strip().upper()


def superadmin_reason(user: Any, *, allow_queries: bool = True) -> str:
    """Return WHY ``user`` holds everything, or ``""`` when they do not.

    ``allow_queries=False`` restricts the answer to the two DB-free signals. Use
    it on hot paths that must not add a query, and on any caller that may run
    while the connection is in a broken transaction.
    """
    if user is None:
        return ""
    if not getattr(user, "is_authenticated", False):
        return ""
    if getattr(user, "is_superuser", False):
        return REASON_DJANGO_SUPERUSER
    if _role_code(getattr(user, "role", None)) == SUPERADMIN_ROLE_CODE:
        return REASON_PRIMARY_ROLE
    if not allow_queries:
        return ""
    roles = getattr(user, "roles", None)
    if roles is None or not hasattr(roles, "filter"):
        return ""
    from django.db import DatabaseError

    try:
        # Global template row only — see the module docstring on why a
        # school-scoped row coded SUPERADMIN must NOT confer god-mode.
        if roles.filter(code=SUPERADMIN_ROLE_CODE, school__isnull=True).exists():
            return REASON_ASSIGNED_ROLE
    except (DatabaseError, AttributeError, TypeError, ValueError):
        return ""
    return ""


def is_platform_superadmin(user: Any, *, allow_queries: bool = True) -> bool:
    """True when ``user`` owns the keys to the kingdom — every permission, present and future."""
    return bool(superadmin_reason(user, allow_queries=allow_queries))


__all__ = [
    "REASON_ASSIGNED_ROLE",
    "REASON_DJANGO_SUPERUSER",
    "REASON_PRIMARY_ROLE",
    "SUPERADMIN_ROLE_CODE",
    "is_platform_superadmin",
    "superadmin_reason",
]
