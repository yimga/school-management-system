"""Per-tenant PWA icon endpoint (v2.60 — Tier 1 gap closure).

The v2.59 manifest endpoint references tenant logos directly, but the PWA
spec requires icons at specific sizes (minimum 192x192 and 512x512) with
matching ``sizes`` declarations, otherwise the browser silently refuses to
install. Tenant logos are uploaded at arbitrary dimensions — so we resize
on the fly here.

Strategy:

* **Raster source (PNG/JPEG/WEBP):** open with Pillow, downscale with
  LANCZOS to the requested size on a transparent canvas. For the
  ``maskable`` variant we composite onto a tinted background with a
  12.5% safe-zone padding (per `web.dev/maskable-icon`), so the OS launcher
  can crop without clipping the mark.
* **Vector source (SVG):** stream the (already-sanitized) SVG bytes with
  ``image/svg+xml``. Browsers honor SVG icons in the manifest when ``type``
  matches — they rasterize themselves. The ``sizes`` slot is purely
  declarative for SVG.
* **No logo on file:** generate a monogram fallback — first letter of
  ``site_name`` on a square tinted with ``primary_color``. Same output
  whether the tenant is brand-new or hasn't uploaded a logo yet.

All responses carry ``Vary: Host`` so a CDN doesn't serve one tenant's
icon to another, plus a 1-day cache header (the icon is host-stable).
"""

from __future__ import annotations

import io
import logging
from typing import Optional

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

# Sizes the manifest can legitimately request. Locking this down stops
# attackers from forcing the server to generate hundreds of unique-size
# rasters as a DoS vector. magic-number-allow: pwa-icon-size-spec
_ALLOWED_SIZES: frozenset[int] = frozenset({16, 32, 48, 96, 144, 192, 256, 384, 512, 1024})  # magic-number-allow: pwa-icon-size-spec

# Maskable icons need a quiet safe zone — the OS may crop up to 10% on
# every edge. We pad more conservatively at 12.5% to survive aggressive
# circular masks.
_MASKABLE_PADDING_RATIO: float = 0.125


def _resolve_effective_settings(request):
    """Wrap the canonical resolver with a defensive fallback."""
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        # config-resolver-allow: namespace returned and fanned into _logo_field/_theme_colors/_site_initial helpers
        return get_effective_site_settings(request=request)
    except (ImportError, RuntimeError, Exception):  # pragma: no cover - defensive
        return None


def _logo_field(settings_obj):
    """Return the logo FieldFile or None."""
    if settings_obj is None:
        return None
    logo = getattr(settings_obj, "logo", None)
    if logo and getattr(logo, "name", ""):
        return logo
    return None


def _logo_bytes_and_kind(logo) -> tuple[Optional[bytes], str]:
    """Read the logo bytes + detect kind ("svg" | "raster" | "")."""
    if logo is None:
        return None, ""
    name = (getattr(logo, "name", "") or "").lower()
    try:
        with logo.open("rb") as fh:
            data = fh.read()
    except (FileNotFoundError, OSError, ValueError) as exc:
        logger.warning("manifest_icon: logo open failed: %s", exc)
        return None, ""
    if not data:
        return None, ""
    if name.endswith(".svg") or data.lstrip()[:200].lower().startswith(b"<?xml") or b"<svg" in data[:1024]:  # magic-number-allow: header-sniff-window
        return data, "svg"
    return data, "raster"


def _hex_to_rgb(value: str, fallback: tuple[int, int, int] = (199, 127, 28)) -> tuple[int, int, int]:  # magic-number-allow: warm-honey-rgb-default
    """Parse #RRGGBB → (r, g, b). Fall back on parse error."""
    if not value:
        return fallback
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        return fallback
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except ValueError:
        return fallback


def _theme_colors(settings_obj) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return ((primary_rgb), (background_rgb)) with platform fallback."""
    primary_hex = (getattr(settings_obj, "primary_color", None) or "#c47f1c") if settings_obj else "#c47f1c"
    background_hex = (getattr(settings_obj, "background_color", None) or "#fdf9f2") if settings_obj else "#fdf9f2"
    return (
        _hex_to_rgb(primary_hex, (199, 127, 28)),  # magic-number-allow: warm-honey-rgb-default
        _hex_to_rgb(background_hex, (253, 249, 242)),  # magic-number-allow: cream-bg-rgb-default
    )


def _site_initial(settings_obj) -> str:
    name = ""
    if settings_obj is not None:
        name = (getattr(settings_obj, "site_name", "") or "")
    name = name.strip() or "RunMyCampus"
    return name[0].upper()


def _draw_bell_clock_companion(draw, size: int, *, stroke_rgb, fill_rgb) -> None:
    """Small bell-clock mark in the corner (canonical geometry from _bell_clock_mark.html)."""
    import math

    pad = max(2, int(size * 0.12))
    cx = size - pad - int(size * 0.18)
    cy = size - pad - int(size * 0.18)
    r_ring = max(3, int(size * 0.14))
    stroke = stroke_rgb + (200,)  # magic-number-allow: companion-ring-alpha
    fill = fill_rgb + (255,)  # magic-number-allow: rgba-opaque-alpha
    draw.ellipse(
        (cx - r_ring, cy - r_ring, cx + r_ring, cy + r_ring),
        outline=stroke,
        width=max(1, size // 64),
    )
    dot_r = max(1, size // 40)
    for idx in (0, 1, 2):
        angle = math.pi / 2 - idx * (math.pi / 3)
        x = cx + (r_ring - dot_r) * math.cos(angle)
        y = cy - (r_ring - dot_r) * math.sin(angle)
        draw.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=fill)


def _render_monogram_png(size: int, *, primary_rgb, background_rgb, initial: str, maskable: bool) -> bytes:
    """Pillow fallback when the tenant has no logo on file."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), background_rgb + (255,))  # magic-number-allow: rgba-opaque-alpha
    draw = ImageDraw.Draw(img)

    opaque_white = (255, 255, 255, 255)  # magic-number-allow: rgba-opaque-white

    if maskable:
        # Solid tinted square fills the entire canvas; the OS will crop.
        draw.rectangle((0, 0, size, size), fill=primary_rgb + (255,))  # magic-number-allow: rgba-opaque-alpha
        text_color = opaque_white
        text_size = int(size * 0.45)
    else:
        # Rounded squircle, primary fill, white monogram. Squircle radius
        # matches the rmc-brand-mark grammar (22% of side).
        radius = int(size * 0.22)
        draw.rounded_rectangle(
            (0, 0, size - 1, size - 1),
            radius=radius,
            fill=primary_rgb + (255,),  # magic-number-allow: rgba-opaque-alpha
        )
        text_color = opaque_white
        text_size = int(size * 0.55)

    # Pillow's default font is bitmap; load DejaVuSans if present for
    # smoother monograms. Falls back silently to default.
    font = None
    for candidate in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            font = ImageFont.truetype(candidate, text_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    try:
        bbox = draw.textbbox((0, 0), initial, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) // 2 - bbox[0]
        ty = (size - th) // 2 - bbox[1]
    except (AttributeError, ValueError):
        tw = th = text_size
        tx = ty = (size - text_size) // 2
    draw.text((tx, ty), initial, fill=text_color, font=font)

    if not maskable:
        accent_rgb = (
            min(255, primary_rgb[0] + 40),  # magic-number-allow: bell-accent-shift
            max(0, primary_rgb[1] - 20),
            max(0, primary_rgb[2] - 40),
        )
        _draw_bell_clock_companion(
            draw,
            size,
            stroke_rgb=background_rgb if background_rgb[0] > 200 else (15, 27, 45),  # magic-number-allow: ink-stroke-rgb
            fill_rgb=accent_rgb,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _resize_raster_png(raster_bytes: bytes, size: int, *, primary_rgb, maskable: bool) -> bytes:
    """Open + resize tenant logo bytes to (size,size). Maskable composites on a tinted background."""
    from PIL import Image

    src = Image.open(io.BytesIO(raster_bytes))
    src.load()
    if src.mode != "RGBA":
        src = src.convert("RGBA")

    if maskable:
        # Maskable: tinted background fills the canvas, the logo sits in
        # a centered safe zone at 75% of side.
        canvas = Image.new("RGBA", (size, size), primary_rgb + (255,))  # magic-number-allow: rgba-opaque-alpha
        inner = size - int(size * _MASKABLE_PADDING_RATIO * 2)
        inner = max(1, inner)
    else:
        # Default: transparent canvas, logo scaled to fit.
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        inner = size

    # Fit src into the inner box preserving aspect.
    src_w, src_h = src.size
    if src_w <= 0 or src_h <= 0:
        return _render_monogram_png(
            size, primary_rgb=primary_rgb,
            background_rgb=(255, 255, 255), initial="R", maskable=maskable,  # magic-number-allow: rgb-white-fallback
        )
    scale = min(inner / src_w, inner / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = src.resize((new_w, new_h), Image.LANCZOS)
    ox = (size - new_w) // 2
    oy = (size - new_h) // 2
    canvas.alpha_composite(resized, (ox, oy))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@require_GET
@cache_control(public=True, max_age=86400)  # magic-number-allow: one-day-cache
def manifest_icon_view(request, size: int, maskable: int = 0):
    """Render a PWA icon at the requested size for the active tenant.

    URL parameters:
      ``size`` (int) — one of the allowed sizes; rejected otherwise.
      ``maskable`` (int) — 1 to render with safe-zone padding for the
                           maskable purpose; 0 (default) for the any purpose.
    """
    if size not in _ALLOWED_SIZES:
        return HttpResponseBadRequest("Unsupported icon size.")

    settings_obj = _resolve_effective_settings(request)
    primary_rgb, background_rgb = _theme_colors(settings_obj)
    is_maskable = bool(maskable)
    logo = _logo_field(settings_obj)
    raw_bytes, kind = _logo_bytes_and_kind(logo)

    if kind == "svg" and raw_bytes:
        # Browsers accept image/svg+xml in the icons[] array; declared
        # ``sizes`` is honored as a hint. The bytes were sanitized on
        # upload by validate_svg_safe so streaming is safe.
        response = HttpResponse(raw_bytes, content_type="image/svg+xml")
    else:
        if kind == "raster" and raw_bytes:
            try:
                png = _resize_raster_png(
                    raw_bytes, size,
                    primary_rgb=primary_rgb, maskable=is_maskable,
                )
            except (OSError, ValueError) as exc:
                logger.warning("manifest_icon: raster resize failed: %s; falling back to monogram", exc)
                png = _render_monogram_png(
                    size, primary_rgb=primary_rgb,
                    background_rgb=background_rgb,
                    initial=_site_initial(settings_obj),
                    maskable=is_maskable,
                )
        else:
            png = _render_monogram_png(
                size, primary_rgb=primary_rgb,
                background_rgb=background_rgb,
                initial=_site_initial(settings_obj),
                maskable=is_maskable,
            )
        response = HttpResponse(png, content_type="image/png")

    # Vary on Host so a CDN never cross-serves a tenant's icon. Long
    # max-age is OK because tenant logo upload re-derives a different URL
    # in the manifest via ?v= cache buster (see _icons_from_tenant).
    response["Vary"] = "Host"
    return response


def icon_any(request, size: int):
    """URL handler: /manifest/icon-<size>.png (purpose: any)."""
    return manifest_icon_view(request, size=int(size), maskable=0)


def icon_maskable(request, size: int):
    """URL handler: /manifest/icon-<size>-maskable.png (purpose: maskable)."""
    return manifest_icon_view(request, size=int(size), maskable=1)
