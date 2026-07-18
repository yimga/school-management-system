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


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_operator_mfa(school=None, *, request=None) -> "OperatorMfaPolicy":
    """The operator's MFA policy for a tenant (Operator + tenant, with floor).

    Operators set this per-tenant WITHOUT a migration through the operator config
    cascade (``RuntimeDefaults`` / ``School.settings['runtime_defaults']``): the
    keys ``mfa_operator_require_all_staff`` and ``mfa_operator_required_roles``.
    No tenant-facing form writes those keys, so a tenant cannot weaken them — and
    because the resolver unions everything (see ``effective_required_roles``), a
    tenant can only tighten. A platform-wide switch
    ``settings.MFA_OPERATOR_REQUIRE_ALL_STAFF`` applies to every tenant.

    Fail-soft: any lookup error yields an empty (no-op) policy, so a broken config
    read never removes MFA that the baseline floor already requires.
    """
    require_all_staff = _truthy(getattr(settings, "MFA_OPERATOR_REQUIRE_ALL_STAFF", ""))
    required_roles: list[str] = []
    if school is not None:
        try:
            from apps.platform_runtime.config_resolver import get_effective_config

            per_tenant_all = get_effective_config(
                school, "mfa_operator_require_all_staff", request=request, default=None
            )
            if per_tenant_all is not None:
                require_all_staff = require_all_staff or _truthy(per_tenant_all)

            roles = get_effective_config(
                school, "mfa_operator_required_roles", request=request, default=None
            )
            if isinstance(roles, (list, tuple)):
                required_roles = [str(r) for r in roles if r]
            elif isinstance(roles, str) and roles.strip():
                required_roles = [
                    part for part in roles.replace(",", " ").split() if part
                ]
        except Exception:  # noqa: BLE001 — a broken config read must never drop MFA
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

from datetime import timedelta

from django.utils import timezone

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
    "effective_required_roles",
    "role_requires_mfa",
    "OperatorMfaPolicy",
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
