"""
Tenant-scoping for views and APIs: filter by request.school and block when school is missing or feature disabled.
"""

from django.http import HttpResponseForbidden


def get_current_school(request):
    """Return request.school or None. Use after TenantMiddleware."""
    return getattr(request, "school", None)


class TenantScopedMixin:
    """
    Mixin for class-based views that need a current school.
    Sets self.school = request.school and returns 403 if no school.
    Subclasses should filter querysets by self.school (or request.school).
    """

    def dispatch(self, request, *args, **kwargs):
        school = getattr(request, "school", None)
        if school is None:
            return HttpResponseForbidden(
                "School context required. Use your school subdomain or select a school."
            )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(qs.model, "school") and getattr(self.request, "school", None):
            return qs.filter(school=self.request.school)
        return qs


def require_school(view_func):
    """Decorator: require request.school; return 403 if missing."""

    def wrapped(request, *args, **kwargs):
        if getattr(request, "school", None) is None:
            return HttpResponseForbidden("School context required.")
        return view_func(request, *args, **kwargs)

    return wrapped


def require_feature(feature_code: str):
    """Decorator factory: require request.school and feature enabled via Policy Registry (is_feature_enabled)."""

    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            school = getattr(request, "school", None)
            if school is None:
                return HttpResponseForbidden("School context required.")
            from apps.schools.models import is_feature_enabled

            if not is_feature_enabled(school, feature_code):
                return HttpResponseForbidden(
                    "This module is not enabled for your school."
                )
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
