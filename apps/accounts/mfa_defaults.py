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

from collections import namedtuple
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


# Roles that ALWAYS require MFA when the user is authenticated. The list is
# normalised to upper-case at lookup time so it matches the role strings
# returned by ``get_user_role`` in apps.accounts.middleware.
BASELINE_REQUIRED_ROLES: tuple[str, ...] = (
    "PLATFORM_ADMIN",
    "PLATFORM_OWNER",
    # Canonical value used by accounts.User.Role. Keep the historical
    # underscore spelling below for imported/legacy role registries.
    "SUPERADMIN",
    "SUPER_ADMIN",
    "FINANCE_ADMIN",
    "FINANCE",
    "BURSAR",
    "SCHOOL_ADMIN",
    "ADMIN",
    "AUDITOR",
)


def principal_requires_strict_mfa(user, school=None) -> bool:
    """Return whether MFA enrollment may never be softened for this principal.

    Trusted-browser windows are still honoured *after* a successful challenge.
    This helper only prevents optional/grace tenant policy from letting a
    platform superadmin or an active school owner enter a privileged workspace
    before they have enrolled MFA.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = str(getattr(user, "role", "") or "").strip().upper()
    if getattr(user, "is_superuser", False) or role in {
        "SUPERADMIN",
        "SUPER_ADMIN",
        "PLATFORM_ADMIN",
        "PLATFORM_OWNER",
    }:
        return True
    if school is None:
        return False
    try:
        from apps.schools.models import SchoolMembership

        return SchoolMembership.objects.filter(
            school_id=getattr(school, "pk", None),
            user_id=getattr(user, "pk", None),
            is_school_owner=True,
            suspended_at__isnull=True,
        ).exists()
    except Exception:  # noqa: BLE001 - fail closed for an ADMIN on a tenant host
        return role == "ADMIN"


def effective_required_roles(
    tenant_required: list[str] | tuple[str, ...] | None,
    operator_required: list[str] | tuple[str, ...] | None = None,
) -> set[str]:
    """Return the union of baseline + operator + tenant + setting-driven roles.

    The set is layered so it can only ever get STRICTER, never weaker:

    * ``BASELINE_REQUIRED_ROLES`` — the platform floor (finance/admin/auditor …);
      neither operator nor tenant can subtract from it.
    * ``operator_required`` — an operator's per-tenant policy (see
      ``resolve_operator_mfa``); a tenant can add to it but not remove it, because
      this is a union.
    * ``tenant_required`` — the tenant's own ``require_mfa_roles``.
    * ``settings.MFA_REQUIRED_ROLES_EXTRA`` — a platform-wide operator lever.

    All entries are normalised to upper-case strings.
    """
    out: set[str] = set()
    for r in BASELINE_REQUIRED_ROLES:
        out.add(r.upper())
    for r in operator_required or ():
        if r:
            out.add(str(r).strip().upper())
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


#: Operator-set MFA policy for a tenant — sits ABOVE the tenant's own settings and
#: BELOW nothing but the baseline floor. A tenant can only ADD to it.
OperatorMfaPolicy = namedtuple("OperatorMfaPolicy", ("require_all_staff", "required_roles"))

#: Where the operator's per-tenant MFA policy is stored on the tenant row. A
#: dedicated key under ``School.settings`` that NO tenant-facing form writes, so a
#: tenant can never weaken it (and, being a union/OR in the resolver, could only
#: tighten anyway). Written by the operator screen
#: (apps/schools/super_views_mfa_policy.py), read here.
OPERATOR_MFA_SETTINGS_KEY = "operator_mfa"


def _truthy(value: object) -> bool:
    if value is True:
        return True
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _split_roles(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(r).strip() for r in value if str(r).strip()]
    if isinstance(value, str) and value.strip():
        return [part for part in value.replace(",", " ").split() if part]
    return []


def read_operator_mfa_settings(school) -> dict:
    """The raw operator-MFA blob stored on a school (``{}`` when unset)."""
    blob = getattr(school, "settings", None)
    if not isinstance(blob, dict):
        return {}
    stored = blob.get(OPERATOR_MFA_SETTINGS_KEY)
    return dict(stored) if isinstance(stored, dict) else {}


def resolve_operator_mfa(school=None, *, request=None) -> "OperatorMfaPolicy":
    """The operator's MFA policy for a tenant (Operator + tenant, with floor).

    Read migration-free from ``School.settings['operator_mfa']`` — a dedicated key
    no tenant-facing form writes, so a tenant cannot weaken it; and because the
    resolver unions everything (see ``effective_required_roles``), a tenant can
    only tighten. A platform-wide switch ``settings.MFA_OPERATOR_REQUIRE_ALL_STAFF``
    applies to every tenant. (This reads the tenant row directly rather than
    ``get_effective_config`` because that resolver only surfaces DECLARED settings
    fields — an arbitrary operator key would be silently dropped.)

    Fail-soft: any lookup error yields an empty (no-op) policy, so a broken read
    never removes MFA that the baseline floor already requires.
    """
    require_all_staff = _truthy(getattr(settings, "MFA_OPERATOR_REQUIRE_ALL_STAFF", ""))
    required_roles: list[str] = []
    if school is not None:
        try:
            stored = read_operator_mfa_settings(school)
            if stored.get("require_all_staff") is not None:
                require_all_staff = require_all_staff or _truthy(
                    stored.get("require_all_staff")
                )
            required_roles = _split_roles(stored.get("required_roles"))
        except Exception:  # noqa: BLE001 — a broken read must never drop MFA
            pass
    return OperatorMfaPolicy(bool(require_all_staff), tuple(required_roles))


# ---------------------------------------------------------------------------
# Enforcement posture — strict / grace / optional (v4.04.5x)
# ---------------------------------------------------------------------------
#
# Best-in-class platforms (Salesforce, AWS, GitHub, Microsoft 365) all mandate
# MFA for privileged roles, but differ in HOW they roll it out: a hard wall on
# the very first navigation reads as "the app is broken", so they SOFT-LAUNCH
# with a persistent nudge, then a grace countdown, and only then a hard wall.
# This resolver lets a tenant/operator pick the posture per-school (or
# platform-wide) via the runtime-defaults cascade
# (RuntimeDefaults.mfa_enforcement_mode / mfa_grace_period_days). The platform
# default is "optional" (nudge-only) — the soft-launch phase — so a brand-new
# owner is never locked out of their own dashboard before they have had a
# chance to enroll. Operators tighten to "grace"/"strict" when ready.
#
# NOTE on "grace": the window is currently anchored on ``user.date_joined``, so
# an EXISTING admin whose account predates the grace window is enforced
# immediately. For a platform-wide rollout to existing users, anchor on the
# enforcement-start date instead (Microsoft 365's 14-day model) — see
# ``resolve_mfa_enforcement`` below. Until that anchor lands, prefer "optional"
# for a platform-wide default and reserve "grace" for new-tenant cohorts.

#: Modes for ``RuntimeDefaults.mfa_enforcement_mode``. "strict" preserves the
#: original hard-wall behavior and is the platform default.
MFA_MODE_STRICT = "strict"
MFA_MODE_GRACE = "grace"
MFA_MODE_OPTIONAL = "optional"
VALID_MFA_ENFORCEMENT_MODES: tuple[str, ...] = (
    MFA_MODE_STRICT,
    MFA_MODE_GRACE,
    MFA_MODE_OPTIONAL,
)

#: Default grace-window length when a tenant selects "grace" but leaves the day
#: count blank. Mirrored as the façade default in
#: ``apps.siteconfig.models_support.virtual_site_setting_default`` ("_ints").
DEFAULT_MFA_GRACE_PERIOD_DAYS = 7

#: Resolver verdict consumed by ``RequireMFAMiddleware`` and the nudge banner.
#: ``action`` is one of: "none" (not required / already enrolled — no-op),
#: "enforce" (hard wall — redirect to setup), "grace" (allow + nudge, deadline
#: known), "nudge" (allow + nudge, no deadline — optional mode).
MfaEnforcementDecision = namedtuple(
    "MfaEnforcementDecision",
    ("action", "mode", "grace_days_remaining", "grace_deadline"),
)


def normalize_mfa_mode(raw: object) -> str:
    """Map a raw stored value to a valid mode, defaulting to strict."""
    value = str(raw or "").strip().lower()
    if value in VALID_MFA_ENFORCEMENT_MODES:
        return value
    return MFA_MODE_STRICT


def resolve_mfa_enforcement(
    *,
    must_have_mfa: bool,
    has_device: bool,
    mode: object,
    grace_period_days: object = None,
    user: object = None,
) -> MfaEnforcementDecision:
    """Decide how to treat a required-role user who may lack an MFA device.

    Only ``must_have_mfa and not has_device`` users are ever gated; everyone
    else returns ``action="none"``. The grace window is anchored on the user's
    ``date_joined`` (no per-user migration needed): a brand-new owner gets the
    full window before any wall, while long-standing admins past the window are
    enforced. ``optional`` never walls — it only nudges.
    """
    norm_mode = normalize_mfa_mode(mode)

    if not must_have_mfa or has_device:
        return MfaEnforcementDecision("none", norm_mode, None, None)

    if norm_mode == MFA_MODE_STRICT:
        return MfaEnforcementDecision("enforce", norm_mode, None, None)

    if norm_mode == MFA_MODE_OPTIONAL:
        return MfaEnforcementDecision("nudge", norm_mode, None, None)

    # grace: allow until date_joined + grace_period_days, then enforce.
    try:
        days = int(grace_period_days)
    except (TypeError, ValueError):
        days = DEFAULT_MFA_GRACE_PERIOD_DAYS
    if days < 0:
        days = DEFAULT_MFA_GRACE_PERIOD_DAYS

    joined = getattr(user, "date_joined", None)
    if joined is None:
        # No anchor (e.g. synthetic request user) — treat as still in grace so a
        # config-only test or odd account is never hard-walled by grace mode.
        return MfaEnforcementDecision("grace", norm_mode, days, None)

    deadline = joined + timedelta(days=days)
    now = timezone.now()
    if now >= deadline:
        return MfaEnforcementDecision("enforce", norm_mode, 0, deadline)
    remaining = (deadline - now).days
    return MfaEnforcementDecision("grace", norm_mode, max(remaining, 0), deadline)


__all__ = [
    "BASELINE_REQUIRED_ROLES",
    "principal_requires_strict_mfa",
    "effective_required_roles",
    "role_requires_mfa",
    "OperatorMfaPolicy",
    "OPERATOR_MFA_SETTINGS_KEY",
    "read_operator_mfa_settings",
    "resolve_operator_mfa",
    "MFA_MODE_STRICT",
    "MFA_MODE_GRACE",
    "MFA_MODE_OPTIONAL",
    "VALID_MFA_ENFORCEMENT_MODES",
    "DEFAULT_MFA_GRACE_PERIOD_DAYS",
    "MfaEnforcementDecision",
    "normalize_mfa_mode",
    "resolve_mfa_enforcement",
]
