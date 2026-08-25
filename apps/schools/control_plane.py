"""
Control-plane access helpers, decorators, and audit logging.

The platform control plane must not rely on tenant RBAC. Keep access checks for
manager-host and /super/ surfaces here so every control-plane entry point uses
the same operator contract.
"""

import logging
import os
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError

logger = logging.getLogger(__name__)


def _operator_roles() -> frozenset[str]:
    """
    Read the env-configurable allowlist of role tokens that grant control-plane
    access on the manager surface.

    Cascade (env-only by design — see the rationale comment below):
        env var CONTROL_PLANE_OPERATOR_ROLES (comma-separated, case-insensitive)
        -> default ("SUPERADMIN",)

    Why env-only and not RuntimeDefaults / admin-UI: granting operator status is
    a privilege-escalation primitive. Routing it through the admin UI would let
    any compromised SUPERADMIN promote arbitrary roles to peer-operator status
    without an auditable code-or-deploy trail. Env vars require infrastructure
    access to change, which is the right blast-radius gate for this control.
    """
    raw = os.getenv("CONTROL_PLANE_OPERATOR_ROLES", "").strip()
    if not raw:
        # role-string-allow: control-plane operator default; SUPERADMIN is the
        # platform-owner role token, not in role_registry (which enumerates
        # tenant-role tokens only - ADMIN/TEACHER/PARENT/STUDENT/PROPRIETOR).
        return frozenset({"SUPERADMIN"})
    return frozenset(part.strip().upper() for part in raw.split(",") if part.strip())


def _user_has_active_operator_profile(user) -> bool:
    try:
        from apps.platform_runtime.models_operator_identity import (
            PlatformOperatorProfile,
        )

        profile = PlatformOperatorProfile.objects.filter(user_id=user.pk).first()
        return bool(
            profile
            and profile.status
            in (
                PlatformOperatorProfile.Status.ACTIVE,
                PlatformOperatorProfile.Status.INVITED,
            )
        )
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        return False


def _user_has_tenant_membership(user) -> bool:
    try:
        from apps.schools.models import SchoolMembership

        # tenant-isolation-allow: operator-plane-user-membership-gate-before-tenant-bind
        return SchoolMembership.objects.filter(user=user).exists()
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        return False


def user_is_tenant_scoped_staff(user) -> bool:
    """True when the user belongs to at least one school (tenant staff)."""
    return _user_has_tenant_membership(user)


def user_has_control_plane_access(user) -> bool:
    """
    Return True only for platform operators.

    Control-plane access is intentionally narrower than tenant staff access:
    tenant staff/admin users must not gain manager-host capabilities.

    Operator-eligible identities:
      - Django superusers (``is_superuser=True``)
      - Users with an active ``PlatformOperatorProfile`` (invited/active tiers)
      - Users whose role is in CONTROL_PLANE_OPERATOR_ROLES **and who are not
        tenant-scoped** (no ``SchoolMembership``). Self-service signup owners
        carry ``ADMIN`` but are tenant staff — they must never pass via role
        alone even when ``CONTROL_PLANE_OPERATOR_ROLES`` includes ``ADMIN``.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if _user_has_active_operator_profile(user):
        return True
    if _user_has_tenant_membership(user):
        return False
    role = (getattr(user, "role", "") or "").upper()
    if bool(role) and role in _operator_roles():
        return True
    return False


def _user_has_super_access(user):
    return user_has_control_plane_access(user)


def is_control_plane_request(request) -> bool:
    return (getattr(request, "public_host_kind", None) or "").lower() == "manager"


def _user_is_tenant_admin_role(user) -> bool:
    """Tenant ADMIN role — the same admin tier that reaches the tenant backend
    dashboard (``accounts.views._is_admin_user`` + ``@permission_required('settings.manage')``).

    Tenant admins are role-based members (``SchoolMembership``); by platform
    design they are NOT Django ``is_staff`` (memory: tenant admins can't use
    Django ``/admin/``). Uses ``User.Role.ADMIN`` (not a hardcoded string).
    """
    try:
        from django.contrib.auth import get_user_model

        role_enum = get_user_model().Role
    except (ImportError, AttributeError):
        return False
    return getattr(user, "role", None) == role_enum.ADMIN


def user_can_access_studio_on_request(request) -> bool:
    """
    Studio OS is mounted on both manager and tenant hosts.

    - **Manager host:** only platform operators (superuser / SUPERADMIN), never generic
      tenant staff. Aligns Studio with the control-plane contract.
    - **Tenant host:** the school-scoped operational Studio is for the tenant admin
      tier (superuser / Django staff / role ADMIN) — the SAME gate as the tenant
      backend dashboard. Gating on ``is_staff`` alone locked out tenant admins
      (who are role-based, never ``is_staff``), bouncing them back to the dashboard
      from every Studio entry point (e.g. guided onboarding → ``studio_os:launch``).
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if (getattr(request, "public_host_kind", None) or "").lower() == "manager":
        return user_has_control_plane_access(user)
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    return _user_is_tenant_admin_role(user)


def use_control_plane_shell(request) -> bool:
    """
    True when the request should see the control-plane UI (same top bar/sidebar as /super/).
    Use for template choice (Studio, Theme & Experience). Includes "local" so localhost
    gets the same shell without requiring manager.localhost.

    Never True on a tenant host — a school's subdomain, custom domain, or sovereign
    appliance must show tenant chrome (school name/logo), not the RunMyCampus operator
    topbar.
    """
    # A school's own appliance NEVER shows operator chrome, whatever the host
    # classification decided. Both checks below read a per-request attribute
    # derived from the Host header, and a school once saw the RunMyCampus operator
    # topbar -- wordmark, ADMIN badge, "Search tenants, incidents, commands" -- on
    # their own box because that derivation went one way it was not expected to.
    # This one is a property of the DEPLOYMENT, so it cannot be wrong per request.
    from django.conf import settings as _settings

    if bool(getattr(_settings, "RMC_IS_SELFHOST_BOX", False)):
        return False
    if getattr(request, "is_tenant_host", False):
        return False
    kind = (getattr(request, "public_host_kind", None) or "").lower()
    if kind == "tenant":
        return False
    return kind in ("manager", "local")


def require_control_plane_access(view_func):
    """
    Restrict view to authenticated platform operators.

    Use for manager-host APIs and operator dashboards outside the /super/
    namespace. /super/ may use require_super_access as an alias.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not user_has_control_plane_access(request.user):
            raise PermissionDenied("Control-plane access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def require_super_access(view_func):
    """
    Restrict view to authenticated users with is_superuser or role=SUPERADMIN.
    Use in addition to TenantSuperAdminRequiredMiddleware for defense-in-depth.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not user_has_control_plane_access(request.user):
            raise PermissionDenied("Super Admin access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _is_super_surface(request) -> bool:
    """True if request is for /super/ or manager host (control-plane surface)."""
    path = (getattr(request, "path", "") or "").strip()
    if path.startswith("/super/"):
        return True
    return is_control_plane_request(request)


def require_super_access_with_host(view_func):
    """
    Restrict view to control-plane surface (manager host or /super/) AND control-plane role.
    Use for all /super/ views so that even if URLconf is misconfigured, views reject non-manager access.
    Enforces: (1) host/surface is manager or path is /super/, (2) user has SUPERADMIN or is_superuser.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _is_super_surface(request):
            raise PermissionDenied(
                "Control-plane surface required (manager host or /super/)."
            )
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not user_has_control_plane_access(request.user):
            raise PermissionDenied("Super Admin access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def rate_limit_super(minute_limit=120):
    """
    Rate limit /super/ view to minute_limit requests per user per minute (cache-based).
    Returns 429 Too Many Requests when exceeded.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            from django.core.cache import cache
            from django.utils import timezone

            key = "super_rl:{}:{}".format(
                request.user.pk,
                timezone.now().strftime("%Y%m%d%H%M"),
            )
            try:
                count = cache.get(key, 0)
                if count >= minute_limit:
                    from django.http import HttpResponse

                    r = HttpResponse("Too Many Requests", status=429)
                    r["Retry-After"] = "60"
                    return r
                cache.set(key, count + 1, timeout=120)
            except (
                ConnectionError,
                OSError,
                TypeError,
                ValueError,
                AttributeError,
            ) as e:
                logger.warning("Super rate limit check failed: %s", e)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def log_control_plane_action(
    request,
    action: str,
    model_name: str,
    object_id: str,
    object_repr: str = "",
    *,
    reason: str = "",
    sensitivity: str = "HIGH",
    old_values: dict = None,
    new_values: dict = None,
    changed_fields: list = None,
):
    """
    Write an audit log entry for a control-plane (super) action.
    Uses compliance.AuditLog. Call from api_approve_school, api_create_school, switch_to_tenant, sync_repair, etc.
    """
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            ip_address=_get_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
            action=action,
            model_name=model_name,
            object_id=str(object_id),
            object_repr=(object_repr or str(object_id))[:500],
            sensitivity=sensitivity,
            old_values=old_values,
            new_values=new_values,
            changed_fields=changed_fields,
            app_label="schools",
            reason=reason[:255] if reason else "",
        )
    except (
        DatabaseError,
        IntegrityError,
        AttributeError,
        TypeError,
        ValueError,
        ImportError,
    ) as e:
        logger.warning("Control plane audit log failed: %s", e)


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
