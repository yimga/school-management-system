"""Platform operator identity — scopes, tiers, and access helpers (control plane only)."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

# Canonical platform scope codes (separate namespace from tenant Permission codes).
PLATFORM_SCOPE_TEAM_READ = "platform.team.read"
PLATFORM_SCOPE_TEAM_MANAGE = "platform.team.manage"
PLATFORM_SCOPE_TEAM_PROMOTE = "platform.team.promote"
PLATFORM_SCOPE_IMPERSONATE = "platform.impersonate"
PLATFORM_SCOPE_PROVISION = "platform.provision.school"
PLATFORM_SCOPE_BILLING_READ = "platform.billing.read"
PLATFORM_SCOPE_BILLING_WRITE = "platform.billing.write"
PLATFORM_SCOPE_AUDIT_EXPORT = "platform.audit.export"
PLATFORM_SCOPE_BREAK_GLASS_ADMIN = "platform.break_glass.admin"
PLATFORM_SCOPE_TENANT_READ = "platform.tenant.read"
PLATFORM_SCOPE_MIGRATION = "platform.migration.manage"
PLATFORM_SCOPE_FLEET = "platform.fleet.manage"
PLATFORM_SCOPE_SECURITY_READ = "platform.security.read"
PLATFORM_SCOPE_SECURITY_WRITE = "platform.security.write"

ALL_PLATFORM_SCOPES: frozenset[str] = frozenset(
    {
        PLATFORM_SCOPE_TEAM_READ,
        PLATFORM_SCOPE_TEAM_MANAGE,
        PLATFORM_SCOPE_TEAM_PROMOTE,
        PLATFORM_SCOPE_IMPERSONATE,
        PLATFORM_SCOPE_PROVISION,
        PLATFORM_SCOPE_BILLING_READ,
        PLATFORM_SCOPE_BILLING_WRITE,
        PLATFORM_SCOPE_AUDIT_EXPORT,
        PLATFORM_SCOPE_BREAK_GLASS_ADMIN,
        PLATFORM_SCOPE_TENANT_READ,
        PLATFORM_SCOPE_MIGRATION,
        PLATFORM_SCOPE_FLEET,
        PLATFORM_SCOPE_SECURITY_READ,
        PLATFORM_SCOPE_SECURITY_WRITE,
    }
)

TIER_SCOPES: dict[str, frozenset[str]] = {
    "observer": frozenset(
        {
            PLATFORM_SCOPE_TEAM_READ,
            PLATFORM_SCOPE_BILLING_READ,
            PLATFORM_SCOPE_TENANT_READ,
            PLATFORM_SCOPE_SECURITY_READ,
        }
    ),
    "support": frozenset(
        {
            PLATFORM_SCOPE_TEAM_READ,
            PLATFORM_SCOPE_IMPERSONATE,
            PLATFORM_SCOPE_AUDIT_EXPORT,
            PLATFORM_SCOPE_TENANT_READ,
            PLATFORM_SCOPE_SECURITY_READ,
        }
    ),
    "fleet": frozenset(
        {
            PLATFORM_SCOPE_TEAM_READ,
            PLATFORM_SCOPE_PROVISION,
            PLATFORM_SCOPE_IMPERSONATE,
            PLATFORM_SCOPE_AUDIT_EXPORT,
            PLATFORM_SCOPE_TENANT_READ,
            PLATFORM_SCOPE_MIGRATION,
            PLATFORM_SCOPE_FLEET,
            PLATFORM_SCOPE_SECURITY_READ,
        }
    ),
    "billing": frozenset(
        {
            PLATFORM_SCOPE_TEAM_READ,
            PLATFORM_SCOPE_BILLING_READ,
            PLATFORM_SCOPE_BILLING_WRITE,
            PLATFORM_SCOPE_AUDIT_EXPORT,
        }
    ),
    "security": frozenset(
        {
            PLATFORM_SCOPE_TEAM_READ,
            PLATFORM_SCOPE_TEAM_MANAGE,
            PLATFORM_SCOPE_TEAM_PROMOTE,
            PLATFORM_SCOPE_IMPERSONATE,
            PLATFORM_SCOPE_AUDIT_EXPORT,
            PLATFORM_SCOPE_TENANT_READ,
            PLATFORM_SCOPE_MIGRATION,
            PLATFORM_SCOPE_FLEET,
            PLATFORM_SCOPE_SECURITY_READ,
            PLATFORM_SCOPE_SECURITY_WRITE,
        }
    ),
    "principal": frozenset(
        {
            PLATFORM_SCOPE_TEAM_READ,
            PLATFORM_SCOPE_TEAM_MANAGE,
            PLATFORM_SCOPE_TEAM_PROMOTE,
            PLATFORM_SCOPE_IMPERSONATE,
            PLATFORM_SCOPE_PROVISION,
            PLATFORM_SCOPE_BILLING_READ,
            PLATFORM_SCOPE_BILLING_WRITE,
            PLATFORM_SCOPE_AUDIT_EXPORT,
            PLATFORM_SCOPE_TENANT_READ,
            PLATFORM_SCOPE_MIGRATION,
            PLATFORM_SCOPE_FLEET,
            PLATFORM_SCOPE_SECURITY_READ,
            PLATFORM_SCOPE_SECURITY_WRITE,
        }
    ),
    "break_glass": frozenset(ALL_PLATFORM_SCOPES),
}

TIER_CHOICES: tuple[tuple[str, str], ...] = tuple(
    (key, key.replace("_", " ").title()) for key in TIER_SCOPES
)

# Canonical platform break-glass operator (migration 0021 + ensure_superadmin).
CANONICAL_PLATFORM_ADMIN_USERNAME = "admin"


def tier_display(tier: str | None) -> str:
    key = (tier or "").strip().lower()
    for value, label in TIER_CHOICES:
        if value == key:
            return label
    return key.replace("_", " ").title() if key else "—"


def is_canonical_platform_admin(user) -> bool:
    return (
        getattr(user, "username", "") or ""
    ).strip().lower() == CANONICAL_PLATFORM_ADMIN_USERNAME


def user_may_offboard_operator(actor, target) -> bool:
    """False for self, canonical admin, or when actor lacks manage scope."""
    if not getattr(actor, "is_authenticated", False):
        return False
    if getattr(target, "pk", None) == getattr(actor, "pk", None):
        return False
    if is_canonical_platform_admin(target):
        return False
    return user_has_platform_scope(actor, PLATFORM_SCOPE_TEAM_MANAGE)


def ensure_platform_operator_profile(user, *, tier: str | None = None) -> None:
    """Idempotent profile sync for superusers and canonical admin."""
    if not getattr(user, "pk", None):
        return
    from apps.platform_runtime.models_operator_identity import PlatformOperatorProfile
    from django.utils import timezone

    resolved_tier = tier
    if resolved_tier is None:
        if is_canonical_platform_admin(user) or getattr(user, "is_superuser", False):
            resolved_tier = "break_glass"
        else:
            resolved_tier = "support"
    PlatformOperatorProfile.objects.update_or_create(
        user_id=user.pk,
        defaults={
            "status": PlatformOperatorProfile.Status.ACTIVE,
            "tier": resolved_tier,
            "mfa_required": True,
            "activated_at": timezone.now(),
        },
    )


def _operator_role_allowlist() -> frozenset[str]:
    from apps.schools.control_plane import _operator_roles

    return _operator_roles()


def queryset_platform_operators() -> QuerySet:
    """Users eligible for the operator plane (roster / session filters)."""
    User = get_user_model()
    role_allow = _operator_role_allowlist()
    q = Q(is_superuser=True)
    if role_allow:
        q |= Q(role__in=role_allow)
    q |= Q(platform_operator_profile__status="active")
    q |= Q(platform_operator_profile__status="invited")
    q |= Q(platform_operator_profile__status="suspended")
    return User.objects.filter(q).distinct().order_by("username")


def user_is_platform_operator(user) -> bool:
    """True for platform operators — NOT generic tenant staff."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    if role and role in _operator_role_allowlist():
        return True
    profile = getattr(user, "platform_operator_profile", None)
    if profile is not None and profile.status in ("active", "invited", "suspended"):
        return True
    return False


def get_operator_profile(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "platform_operator_profile", None)


@lru_cache(maxsize=1)
def _tier_scopes_map() -> dict[str, frozenset[str]]:
    return {k: frozenset(v) for k, v in TIER_SCOPES.items()}


def user_effective_platform_scopes(user) -> frozenset[str]:
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    if getattr(user, "is_superuser", False):
        return ALL_PLATFORM_SCOPES
    scopes: set[str] = set()
    profile = get_operator_profile(user)
    if profile is not None:
        tier = (profile.tier or "observer").lower()
        scopes.update(_tier_scopes_map().get(tier, frozenset()))
        extra = profile.extra_scopes or []
        if isinstance(extra, list):
            scopes.update(str(c) for c in extra if c in ALL_PLATFORM_SCOPES)
    role = (getattr(user, "role", "") or "").upper()
    if role in _operator_role_allowlist():
        scopes.update(_tier_scopes_map().get("principal", frozenset()))
    return frozenset(scopes)


def user_has_platform_scope(user, *codes: str) -> bool:
    if not codes:
        return False
    if getattr(user, "is_superuser", False):
        return True
    effective = user_effective_platform_scopes(user)
    return any(code in effective for code in codes)


def require_platform_scope(*codes: str):
    """Decorator for /super/ views requiring platform.* scopes."""
    from functools import wraps

    from django.contrib.auth.views import redirect_to_login
    from django.http import HttpResponseForbidden

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if not user or not getattr(user, "is_authenticated", False):
                return redirect_to_login(request.get_full_path())
            from apps.schools.control_plane import user_has_control_plane_access

            if not user_has_control_plane_access(user):
                return HttpResponseForbidden("Control-plane access required.")
            if not user_has_platform_scope(user, *codes):
                return HttpResponseForbidden("Platform scope required.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def operator_mfa_enrolled(user) -> bool:
    from apps.accounts.mfa_setup_flow import mfa_has_device

    return mfa_has_device(user)


def list_active_operators_for_peer_picker(exclude_user_id: int | None = None) -> QuerySet:
    qs = queryset_platform_operators().filter(
        Q(platform_operator_profile__status="active") | Q(is_superuser=True)
    )
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)
    return qs.filter(is_active=True).order_by("email", "username")


def audit_operator_action(request, *, action: str, model_name: str, object_id: str, object_repr: str = "", new_values: dict | None = None):
    from apps.schools.control_plane import log_control_plane_action

    log_control_plane_action(
        request,
        action,
        model_name,
        object_id,
        object_repr=object_repr,
        reason="platform-operator-identity",
        sensitivity="CRITICAL",
        new_values=new_values,
    )
