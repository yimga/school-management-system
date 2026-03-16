"""
Control-plane access helpers, decorators, and audit logging.

The platform control plane must not rely on tenant RBAC. Keep access checks for
manager-host and /super/ surfaces here so every control-plane entry point uses
the same operator contract.
"""
import logging
from functools import wraps

from django.db import DatabaseError, IntegrityError
from django.http import HttpResponseForbidden

logger = logging.getLogger(__name__)


def user_has_control_plane_access(user) -> bool:
    """
    Return True only for platform operators.

    Control-plane access is intentionally narrower than tenant staff access:
    tenant staff/admin users must not gain manager-host capabilities.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return (getattr(user, "role", "") or "").upper() == "SUPERADMIN"


def _user_has_super_access(user):
    return user_has_control_plane_access(user)


def is_control_plane_request(request) -> bool:
    return (getattr(request, "public_host_kind", None) or "").lower() == "manager"


def use_control_plane_shell(request) -> bool:
    """
    True when the request should see the control-plane UI (same top bar/sidebar as /super/).
    Use for template choice (Studio, Theme & Experience). Includes "local" so localhost
    gets the same shell without requiring manager.localhost.
    """
    kind = (getattr(request, "public_host_kind", None) or "").lower()
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
            return HttpResponseForbidden("Control-plane access required.")
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
            return HttpResponseForbidden("Super Admin access required.")
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
            return HttpResponseForbidden("Control-plane surface required (manager host or /super/).")
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not user_has_control_plane_access(request.user):
            return HttpResponseForbidden("Super Admin access required.")
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
            except (ConnectionError, OSError, TypeError, ValueError, AttributeError) as e:
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
    except (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError, ImportError) as e:
        logger.warning("Control plane audit log failed: %s", e)


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
