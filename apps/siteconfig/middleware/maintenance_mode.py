from django.core.cache import cache
from django.shortcuts import render

from apps.siteconfig.models import SiteSettings

CACHE_KEY = "site_settings_v1"
CACHE_TTL = 60


class MaintenanceModeMiddleware:
    """
    If maintenance_mode is enabled in SiteSettings, show a maintenance page
    for all users except superusers, and allow /admin/ + /authentication/ routes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_maintenance_enabled():
        # Cache only primitives to avoid model pickling issues in tests/reloads.
        cached = None
        try:
            cached = cache.get(CACHE_KEY)
        except Exception:
            try:
                cache.delete(CACHE_KEY)
            except Exception:
                pass

        if isinstance(cached, dict) and "maintenance_mode" in cached:
            return bool(cached.get("maintenance_mode"))

        site = None
        try:
            site = SiteSettings.get_solo()
        except Exception:
            site = None
        enabled = bool(getattr(site, "maintenance_mode", False))

        try:
            cache.set(CACHE_KEY, {"maintenance_mode": enabled}, CACHE_TTL)
        except Exception:
            pass

        return enabled

    def __call__(self, request):
        # Allow admin, auth, and health routes (so load balancers / Render always get 200 when app is up)
        if (
            request.path.startswith("/admin/")
            or request.path.startswith("/authentication/")
            or request.path.startswith("/health/")
            or request.path.startswith("/healthz/")
        ):
            return self.get_response(request)

        # request.user may not exist if AuthenticationMiddleware isn't loaded yet
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False):
            return self.get_response(request)

        if self._is_maintenance_enabled():
            site = None
            try:
                site = SiteSettings.get_solo()
            except Exception:
                site = None
            return render(request, "maintenance.html", {"SITE": site}, status=503)

        return self.get_response(request)
