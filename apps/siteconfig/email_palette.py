"""
Branded email palette resolver.

Email templates cannot rely on CSS variables — most clients strip <style> blocks
and none support `var()` reliably. So every color must reach the inline style
attribute as a literal value. To keep that maintainable we resolve a single
palette dict once (from SiteSettings / platform defaults) and templates
reference `{{ brand_email.<role> }}` instead of hardcoded hex literals.

Usage from a request-bound render (context processor handles this automatically):
    html = render_to_string("emails/welcome.html", ctx, request=request)

Usage from a request-free render (Celery task, management command):
    from apps.siteconfig.email_palette import resolve_email_palette
    ctx["brand_email"] = resolve_email_palette(site=site_settings)
    html = render_to_string("emails/welcome.html", ctx)
"""

from __future__ import annotations

from django.conf import settings


def _coerce_hex(value, fallback: str) -> str:
    """Return a clean #rrggbb string or the fallback if the input is unusable."""
    if not value:
        return fallback
    try:
        s = str(value).strip()
    except (TypeError, ValueError):
        return fallback
    if not s.startswith("#"):
        s = "#" + s.lstrip("#")
    # Only accept #rgb or #rrggbb. rgba/hsl/named colors fall back so the
    # downstream _mix_tint never explodes on int() conversion.
    body = s[1:]
    if len(body) not in (3, 6):
        return fallback
    try:
        int(body, 16)
    except ValueError:
        return fallback
    return s


def _mix_tint(hex_color: str, alpha: float) -> str:
    """Return `rgba(r, g, b, alpha)` from a #rgb/#rrggbb string.

    Used to pre-mix accent/primary tint surfaces; emails can't do color-mix().
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except (ValueError, IndexError):
        # Defensive: never break email rendering on a malformed tenant color.
        return f"rgba(79, 70, 229, {alpha})"
    return f"rgba({r}, {g}, {b}, {alpha})"


def resolve_email_palette(site=None, request=None) -> dict:
    """Return the full branded palette for email rendering.

    Order of precedence:
      1. Explicit `site` argument (a SiteSettings-like object with
         `primary_color` / `accent_color` attrs).
      2. `request.site_settings` if a request is supplied.
      3. Platform defaults (indigo + emerald — match base_branded.html fallbacks).

    The returned dict is suitable for direct template use via
    `{{ brand_email.<role> }}`.
    """
    if site is None and request is not None:
        site = getattr(request, "site_settings", None) or getattr(
            request, "school", None
        )

    primary = _coerce_hex(
        getattr(site, "primary_color", None) if site else None,
        settings.PLATFORM_PALETTE_PRIMARY,
    )
    accent = _coerce_hex(
        getattr(site, "accent_color", None) if site else None,
        settings.PLATFORM_PALETTE_ACCENT,
    )

    return {
        # Brand (tenant-driven)
        "primary": primary,
        "accent": accent,
        # Ink (text). Slate scale — Apple-tier dark-on-light hierarchy.
        "ink": "#0f172a",          # primary text
        "ink_muted": "#475569",    # secondary body text
        "ink_subtle": "#64748b",   # meta labels, footer headings
        "ink_faint": "#94a3b8",    # footer body
        "ink_ghost": "#cbd5e1",    # copyright line, dividers
        # Surfaces
        "bg": "#ffffff",
        "bg_soft": "#f8fafc",
        "rule": "rgba(15, 23, 42, 0.06)",
        # Semantic
        "success": "#10b981",
        "warning": "#d97706",
        "danger": "#dc2626",
        # Pre-mixed tints for data-card backgrounds (no color-mix() in email).
        "primary_tint": _mix_tint(primary, 0.08),
        "accent_tint": _mix_tint(accent, 0.08),
        "danger_tint": _mix_tint("#dc2626", 0.04),
    }


def brand_email_processor(request):
    """Template context processor — exposes `brand_email` to every render.

    For email-sending code paths that render WITHOUT a request (Celery tasks,
    management commands), call `resolve_email_palette()` directly and merge
    the result into the explicit context dict.
    """
    site = None
    if request is not None:
        site = getattr(request, "site_settings", None) or getattr(
            request, "school", None
        )
    return {"brand_email": resolve_email_palette(site=site, request=request)}
