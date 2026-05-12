"""
Platform palette context processor.

Exposes the `platform_palette` dict to every Django template so they can reference
`{{ platform_palette.primary }}` instead of `|default:'#4f46e5'` and friends.

Values come from `settings.PLATFORM_PALETTE_*` (env-driven, see config/settings.py).
This matches the established pattern for `brand_email` (transactional email palette)
and `palette_default_*` server-rendered fallbacks.

Used by:
    - admin/components/admin_dashboard_palette_selector.html (palette pack swatches)
    - studio_os/partials/subpages/experience_compare.html (value comparison swatches)
    - marketing/base_marketing.html (--mkt-* CSS variable defaults)

White-label operators that ship the platform under their own brand override these
via env vars (PLATFORM_PALETTE_PRIMARY=#0f172a etc.) so even pre-tenant UI surfaces
(signup pages, palette previews) match their identity without code changes.
"""

from __future__ import annotations

from django.conf import settings


def platform_palette_processor(request):
    """Inject `platform_palette` into template context."""
    return {
        "platform_palette": {
            "primary": settings.PLATFORM_PALETTE_PRIMARY,
            "accent": settings.PLATFORM_PALETTE_ACCENT,
            "surface": settings.PLATFORM_PALETTE_SURFACE,
            "dashboard_bg": settings.PLATFORM_PALETTE_DASHBOARD_BG,
            "hero_bg": settings.PLATFORM_PALETTE_HERO_BG,
            "muted_swatch": settings.PLATFORM_PALETTE_MUTED_SWATCH,
            "border_light": settings.PLATFORM_PALETTE_BORDER_LIGHT,
            "success": settings.PLATFORM_PALETTE_SUCCESS,
            "warning": settings.PLATFORM_PALETTE_WARNING,
            "danger": settings.PLATFORM_PALETTE_DANGER,
        }
    }
