from django.core.cache import cache
from django.db import DatabaseError
from django.shortcuts import render

from apps.platform_runtime.helpers import get_effective_site_settings
from apps.siteconfig.cache_utils import tenant_cache_key

CACHE_KEY = "site_settings_v1"
CACHE_TTL = 60
OPTIONAL_CACHE_ERRORS = (AttributeError, DatabaseError, OSError, RuntimeError, TypeError, ValueError)


class MaintenanceModeMiddleware:
    """
    If maintenance_mode is enabled in SiteSettings, show a maintenance page
    for all users except superusers, and allow /admin/ + /authentication/ routes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_maintenance_enabled(request=None):
        # Cache only primitives to avoid model pickling issues in tests/reloads.
        cache_key = tenant_cache_key(CACHE_KEY, request)
        cached = None
        try:
            cached = cache.get(cache_key)
        except OPTIONAL_CACHE_ERRORS:
            try:
                cache.delete(cache_key)
            except OPTIONAL_CACHE_ERRORS:
                pass

        if isinstance(cached, dict) and "maintenance_mode" in cached:
            return bool(cached.get("maintenance_mode"))

        site = get_effective_site_settings(request=request)
        if callable(getattr(site, "get_feature_control_settings", None)):
            enabled = bool(
                site.get_feature_control_settings().get("maintenance_mode", False)
            )
        else:
            enabled = bool(getattr(site, "maintenance_mode", False))

        try:
            cache.set(cache_key, {"maintenance_mode": enabled}, CACHE_TTL)
        except OPTIONAL_CACHE_ERRORS:
            pass

        return enabled

    def __call__(self, request):
        # Allow admin, auth, and health routes (so load balancers / Render always get 200 when app is up)
        if (
            request.path.startswith("/admin/")
            or request.path.startswith("/authentication/")
            or request.path.startswith("/health/")
            or request.path.startswith("/healthz/")
            or request.path.startswith("/ready")
            or request.path.startswith("/status/")
            or request.path.startswith("/api/health/")
        ):
            return self.get_response(request)

        # request.user may not exist if AuthenticationMiddleware isn't loaded yet
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False):
            return self.get_response(request)

        if self._is_maintenance_enabled(request):
            site = get_effective_site_settings(request=request)
            return render(request, "maintenance.html", {"SITE": site}, status=503)

        return self.get_response(request)
