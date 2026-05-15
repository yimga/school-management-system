"""Per-tenant PWA manifest endpoint (v2.58).

Replaces the static ``static/manifest.json`` and ``static/manifest-portal.json``
files with a Django-rendered manifest that pulls name / short_name /
theme_color / background_color / icons from the request's tenant context.

When the host is platform (manager.runmycampus.com, runmycampus.com with no
tenant resolution) we render the platform defaults; when the host is a
tenant subdomain we render that tenant's actual brand. This is the missing
piece in the brand cascade — every other surface already binds to
SiteSettings, but the manifest icons + names were platform-static.

Both routes (``/manifest.json`` and ``/manifest-portal.json``) point at this
view; the URL kwarg distinguishes the two shapes.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET


def _get_context_value(request, *attr_paths, default=None):
    """Return the first non-empty attribute from the request context.

    Each ``attr_paths`` item is a dotted path like ``"SITE.site_name"`` that
    we resolve against the request. Used to mirror the template context the
    rest of the platform reads from without re-running the full context
    processor.
    """
    for path in attr_paths:
        obj = request
        ok = True
        for part in path.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                ok = False
                break
        if ok and obj not in (None, ""):
            return obj
    return default


def _icons_from_tenant(request) -> list[dict]:
    """Build the icons[] array preferring tenant logos.

    Tenant logo URL (when set) is reused for the icon entries. If absent we
    fall back to the platform-static icon files. Browsers only honor the
    sizes attribute, not file inspection, so the same URL can satisfy
    multiple slots; tenants who care about pixel-perfect maskable icons can
    upload distinct files via their SiteSettings admin.
    """
    site = getattr(request, "SITE", None)
    logo_url = ""
    favicon_url = ""
    if site is not None:
        try:
            logo_url = (
                getattr(getattr(site, "logo", None), "url", "")
                or getattr(site, "logo_url", "")
                or ""
            )
        except (AttributeError, ValueError):
            logo_url = ""
        try:
            favicon_url = getattr(site, "favicon_url", "") or ""
        except (AttributeError, ValueError):
            favicon_url = ""

    big_src = logo_url or "/static/images/icon-512.png"
    small_src = favicon_url or logo_url or "/static/images/icon-192.png"

    return [
        {"src": small_src, "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": big_src, "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ]


def _color(request, primary_attr: str, fallback: str) -> str:
    site = getattr(request, "SITE", None)
    if site is not None:
        value = getattr(site, primary_attr, None)
        if value:
            return str(value)
    return fallback


@require_GET
@cache_control(public=True, max_age=300)
def manifest_view(request, *, scope: str = "platform"):
    """Render manifest.json for the active tenant + scope.

    ``scope="platform"`` → public marketing / manager shell manifest.
    ``scope="portal"``   → tenant portal (parent/teacher/student) manifest.
    """
    site = getattr(request, "SITE", None)
    site_name = (
        _get_context_value(request, "SITE.site_name", default=None)
        or "RunMyCampus"
    )
    short_name = (site_name or "RunMyCampus")[:12] or "RunMyCampus"

    if scope == "portal":
        name = f"{site_name} Portal"
        short = (short_name[:8] + " Portal") if len(short_name) <= 6 else f"{short_name} Portal"
        start_url = "/portal/"
        description = f"{site_name} family portal — grades, attendance, messages."
    else:
        name = site_name
        short = short_name
        start_url = "/"
        description = (
            getattr(site, "tagline", None)
            if site is not None else None
        ) or "Multi-tenant school management platform."

    # Theme color: prefer tenant primary, fallback to platform warm-bright honey.
    theme_color = _color(request, "primary_color", "#c47f1c")
    background_color = _color(request, "background_color", "#fdf9f2")

    payload = {
        "name": name,
        "short_name": short,
        "start_url": start_url,
        "display": "standalone",
        "background_color": background_color,
        "theme_color": theme_color,
        "description": description,
        "icons": _icons_from_tenant(request),
        "scope": "/",
        "orientation": "portrait-primary",
        "lang": getattr(request, "LANGUAGE_CODE", None) or "en",
    }

    if scope == "portal":
        payload["shortcuts"] = [
            {
                "name": "Dashboard",
                "short_name": "Home",
                "description": "Open the portal dashboard.",
                "url": "/portal/",
                "icons": _icons_from_tenant(request)[:1],
            },
            {
                "name": "Calendar",
                "short_name": "Calendar",
                "description": "Unified family calendar.",
                "url": "/portal/unified-calendar/",
                "icons": _icons_from_tenant(request)[:1],
            },
        ]

    response = JsonResponse(payload)
    # Browsers fetch the manifest with credentials=omit by default; allow
    # cross-origin reads for cached CDN delivery while preventing stale
    # tenant data from being served to a different host.
    response["Vary"] = "Host"
    return response


def platform_manifest(request):
    """URL handler: /manifest.json"""
    return manifest_view(request, scope="platform")


def portal_manifest(request):
    """URL handler: /manifest-portal.json"""
    return manifest_view(request, scope="portal")
