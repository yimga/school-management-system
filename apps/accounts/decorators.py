from functools import wraps
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseForbidden

from apps.siteconfig.models import SiteSettings


def _has_any_role(user, roles: tuple[str, ...]) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) in roles:
        return True
    return user.roles.filter(code__in=roles).exists()


def role_required(*roles: str):
    def check(user):
        return _has_any_role(user, roles)
    return user_passes_test(check)


def permission_required(*codes: str):
    def check(user):
        if not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return any(user.has_feature_permission(code) for code in codes)
    return user_passes_test(check)


def portal_toggle_required(flag_name: str, message: str):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            site = SiteSettings.get_solo()
            if not getattr(site, flag_name, True):
                return HttpResponseForbidden(message)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


parent_portal_required = portal_toggle_required("enable_parent_portal", "Parent portal is disabled.")
teacher_portal_required = portal_toggle_required("enable_teacher_portal", "Teacher portal is disabled.")
