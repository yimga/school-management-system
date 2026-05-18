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


def _logo_version_token(request) -> str:
    """Cache buster derived from the active logo so a re-upload invalidates icons.

    Browsers honor manifest URL identity — pointing at the same path means
    they may serve a stale install icon for days. By tagging the icon URL
    with a token derived from the file mtime / size we force a re-fetch
    when the tenant uploads a new logo.
    """
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        settings_obj = get_effective_site_settings(request=request)
    except (ImportError, RuntimeError, Exception):
        return ""
    if settings_obj is None:
        return ""
    logo = getattr(settings_obj, "logo", None)
    if not (logo and getattr(logo, "name", "")):
        return ""
    try:
        # Storage.size + storage.modified is cheap on local FS; cloud
        # backends usually answer .size from object metadata.
        s = logo.size  # type: ignore[attr-defined]
        return f"{s}"
    except (AttributeError, OSError, NotImplementedError):
        # Fallback to the storage name (changes when re-uploaded under hashed-name).
        return str(getattr(logo, "name", ""))[-12:]


def _icons_from_tenant(request) -> list[dict]:
    """Build the icons[] array using the per-tenant icon endpoints.

    v2.60 (Tier 1 gap closure): point at the sized endpoints in
    ``views_manifest_icon`` so every entry actually matches its declared
    ``sizes`` attribute — Chrome / Edge / Android otherwise refuse to mark
    the app as installable. The endpoints resize the tenant logo on the
    fly with Pillow (LANCZOS) or fall back to a tinted monogram square
    when no logo is on file.
    """
    from django.urls import NoReverseMatch, reverse

    v = _logo_version_token(request)
    qs = f"?v={v}" if v else ""

    def _url(name: str, **kwargs) -> str:
        try:
            return reverse(name, kwargs=kwargs) + qs
        except NoReverseMatch:
            # Defensive fallback — should only happen pre-urls-registered in tests.
            size = kwargs.get("size", 192)  # magic-number-allow: pwa-min-icon-size
            return f"/manifest/icon-{size}.png{qs}"

    # Phase 4 #9 — bell-clock companion icon. The platform brand mark renders
    # alongside the tenant logo so the bell-clock signal is recognizable at
    # install-prompt and home-screen sizes. Vector SVG — any size, no resize.
    from django.templatetags.static import static as static_url
    bell_clock_src = static_url("images/runmycampus-icon-bell.svg")

    return [
        {
            "src": bell_clock_src + (qs if qs else ""),
            "sizes": "any",
            "type": "image/svg+xml",
            "purpose": "any",
        },
        {
            "src": _url("pwa_manifest_icon_any", size=192),  # magic-number-allow: pwa-min-icon-size
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any",
        },
        {
            "src": _url("pwa_manifest_icon_any", size=512),  # magic-number-allow: pwa-installable-icon-size
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any",
        },
        {
            "src": _url("pwa_manifest_icon_maskable", size=192),  # magic-number-allow: pwa-min-icon-size
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "maskable",
        },
        {
            "src": _url("pwa_manifest_icon_maskable", size=512),  # magic-number-allow: pwa-installable-icon-size
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "maskable",
        },
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
