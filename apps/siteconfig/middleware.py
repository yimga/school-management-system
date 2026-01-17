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

    def __call__(self, request):
        # Allow admin + auth routes always
        if request.path.startswith("/admin/") or request.path.startswith("/authentication/"):
            return self.get_response(request)

        # request.user may not exist if AuthenticationMiddleware isn't loaded yet
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False):
            return self.get_response(request)

        site = cache.get(CACHE_KEY)
        if site is None:
            try:
                site = SiteSettings.get_solo()
            except Exception:
                site = None
            cache.set(CACHE_KEY, site, CACHE_TTL)

        if site and getattr(site, "maintenance_mode", False):
            return render(request, "maintenance.html", {"SITE": site}, status=503)

        return self.get_response(request)

