"""Hardened MFA-required-roles defaults.

Augments ``RequireMFAMiddleware`` (apps/accounts/middleware.py:588) with a
baseline set of roles that ALWAYS require MFA, regardless of per-tenant
``site.require_mfa_roles`` configuration. Tenants can extend this list, but
they cannot subtract from it.

Why baseline matters: a tenant who forgets to configure MFA still gets the
correct posture for high-risk roles. Per the security audit, MFA was opt-in
even for finance / super-admin roles — this module closes that gap.
"""

from __future__ import annotations

from django.conf import settings


# Roles that ALWAYS require MFA when the user is authenticated. The list is
# normalised to upper-case at lookup time so it matches the role strings
# returned by ``get_user_role`` in apps.accounts.middleware.
BASELINE_REQUIRED_ROLES: tuple[str, ...] = (
    "PLATFORM_ADMIN",
    "PLATFORM_OWNER",
    "SUPER_ADMIN",
    "FINANCE_ADMIN",
    "FINANCE",
    "BURSAR",
    "SCHOOL_ADMIN",
    "ADMIN",
    "AUDITOR",
)


def effective_required_roles(tenant_required: list[str] | tuple[str, ...] | None) -> set[str]:
    """Return the union of baseline + tenant-configured + setting-driven roles.

    All entries are normalised to upper-case strings.
    """
    out: set[str] = set()
    for r in BASELINE_REQUIRED_ROLES:
        out.add(r.upper())
    for r in tenant_required or ():
        if r:
            out.add(str(r).strip().upper())
    extra = getattr(settings, "MFA_REQUIRED_ROLES_EXTRA", ()) or ()
    for r in extra:
        if r:
            out.add(str(r).strip().upper())
    return out


def role_requires_mfa(role: str | None, tenant_required: list[str] | tuple[str, ...] | None) -> bool:
    """True when the user's role falls under the effective required set."""
    if not role:
        return False
    return str(role).strip().upper() in effective_required_roles(tenant_required)


__all__ = [
    "BASELINE_REQUIRED_ROLES",
    "effective_required_roles",
    "role_requires_mfa",
]
