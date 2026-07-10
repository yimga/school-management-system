"""Theme intelligence — in-process colour math, no network.

Helpers used by :mod:`services.ai_palette` and the theme builder palette
endpoint. The contract is *strictly in-process*:

* Pillow is the only optional dependency. If it is not importable we log a
  WARNING and return an honest fallback colour — we never raise.
* NO httpx / requests / urllib / aiohttp imports anywhere in this module.
  An import-scan test in ``services/tests/test_theme_intelligence.py``
  enforces this.
* WCAG ratios use the canonical W3C formula (`Web Content Accessibility
  Guidelines 2.2 §1.4.3`).

Public surface:
* :func:`extract_dominant_colors_from_image`
* :func:`harmonize_for_dark`
* :func:`wcag_contrast_ratio`
* :func:`wcag_grade`
* :class:`ExtractedColor`
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

__all__ = [
    "ExtractedColor",
    "ColorSource",
    "extract_dominant_colors_from_image",
    "harmonize_for_dark",
    "wcag_contrast_ratio",
    "wcag_grade",
]


ColorSource = Literal["pillow_quantize", "fallback"]


@dataclass(frozen=True)
class ExtractedColor:
    """A single dominant colour result with provenance."""

    hex: str
    weight: float
    source: ColorSource


_FALLBACK_HEX = "#4F46E5"  # RMC indigo


def _decode_data_uri_to_bytes(value: str) -> bytes | None:
    """Decode a base64 ``data:`` URI to raw bytes; return None if it is not one.

    We never fetch the network, so a plain http(s) URL cannot be turned into
    bytes here and yields None (the caller then degrades to the fallback).
    """
    if not value.startswith("data:"):
        return None
    marker = ";base64,"
    idx = value.find(marker)
    if idx == -1:
        return None
    import base64
    import binascii

    try:
        return base64.b64decode(value[idx + len(marker) :], validate=False)
    except (binascii.Error, ValueError):
        return None


# ---------------------------------------------------------------------------
# Logo / image dominant-colour extraction
# ---------------------------------------------------------------------------


def extract_dominant_colors_from_image(
    image_bytes: bytes | str,
    *,
    max_colors: int = 5,
) -> list[ExtractedColor]:
    """Quantize an image into its dominant colours.

    Uses Pillow's ``Image.quantize`` when the library is importable.
    Otherwise emits a WARNING and returns the indigo fallback so callers
    can continue without branching on availability.

    The function NEVER reaches the network — we read from the in-memory
    ``image_bytes`` only.

    Returns
    -------
    list[ExtractedColor]
        At least one entry. The first entry is the heaviest colour.
    """
    if not image_bytes:
        logger.warning("theme_intelligence: empty image bytes; returning fallback")
        return [ExtractedColor(hex=_FALLBACK_HEX, weight=1.0, source="fallback")]

    if isinstance(image_bytes, str):
        # Some callers pass a string rather than raw bytes — e.g.
        # ``School.logo_url`` is a URLField. We never touch the network (see the
        # docstring), so a bare http(s) URL cannot be turned into bytes; only an
        # in-memory base64 data-URI can. Anything else degrades to the fallback
        # WITHOUT raising — previously the string reached ``io.BytesIO(str)`` and
        # logged a TypeError traceback on every day-1 palette resolution.
        decoded = _decode_data_uri_to_bytes(image_bytes)
        if decoded is None:
            logger.debug(
                "theme_intelligence: received a non-data-URI string; cannot "
                "extract colours without bytes, returning fallback"
            )
            return [ExtractedColor(hex=_FALLBACK_HEX, weight=1.0, source="fallback")]
        image_bytes = decoded

    try:
        pil_image = importlib.import_module("PIL.Image")
    except ImportError:
        logger.warning(
            "theme_intelligence: Pillow not available; returning fallback colour"
        )
        return [ExtractedColor(hex=_FALLBACK_HEX, weight=1.0, source="fallback")]

    try:
        import io

        img = pil_image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        # Quantize down to a small palette — operator brand assets are
        # rarely more than 5 dominant colours.
        n = max(1, min(int(max_colors), 16))
        quantized = img.quantize(colors=n, method=2)  # 2 = MAXCOVERAGE
        palette = quantized.getpalette() or []
        # getcolors returns [(count, palette_index), ...]
        counts = quantized.getcolors() or []
        total = sum(c for c, _ in counts) or 1
        results: list[ExtractedColor] = []
        for count, idx in sorted(counts, key=lambda x: -x[0]):
            base = idx * 3
            if base + 2 >= len(palette):
                continue
            r, g, b = palette[base], palette[base + 1], palette[base + 2]
            results.append(
                ExtractedColor(
                    hex=_rgb_to_hex(r, g, b),
                    weight=round(count / total, 6),
                    source="pillow_quantize",
                )
            )
            if len(results) >= n:
                break
        if not results:
            return [
                ExtractedColor(hex=_FALLBACK_HEX, weight=1.0, source="fallback")
            ]
        return results
    except Exception:  # noqa: BLE001 — honest fallback, never raise into caller
        logger.warning(
            "theme_intelligence: image quantize failed; returning fallback",
            exc_info=True,
        )
        return [ExtractedColor(hex=_FALLBACK_HEX, weight=1.0, source="fallback")]


# ---------------------------------------------------------------------------
# Dark-mode harmonisation
# ---------------------------------------------------------------------------


def harmonize_for_dark(light_palette: dict[str, str]) -> dict[str, str]:
    """Flip a light-mode 11-stop palette into a dark-mode variant.

    Strategy:
    * Lightness is inverted around the midpoint (a 50→950 swap).
    * Hue is preserved within ±10° (we don't shift; we only re-saturate).
    * Saturation is gently boosted (×1.05, clamped to 1.0) at the bright
      end to compensate for the perceived chroma loss on dark surfaces.

    Returns a NEW dict; the input is not mutated.
    """
    if not isinstance(light_palette, dict) or not light_palette:
        return {}

    inverted: dict[str, str] = {}
    # We pair stop ↔ stop by index inversion (50↔950, 100↔900, ...).
    keys_order = [
        "50",
        "100",
        "200",
        "300",
        "400",
        "500",
        "600",
        "700",
        "800",
        "900",
        "950",
    ]
    for i, key in enumerate(keys_order):
        partner_key = keys_order[len(keys_order) - 1 - i]
        partner_hex = light_palette.get(partner_key)
        if not isinstance(partner_hex, str):
            partner_hex = light_palette.get(key, "#000000") if isinstance(light_palette.get(key), str) else "#000000"
        h, s, _l = _hex_to_hsl(partner_hex)
        # Compute target lightness from THIS stop's role in dark mode:
        # mirror the light table.
        light_anchor = {
            "50": 9.0,
            "100": 16.0,
            "200": 24.0,
            "300": 32.0,
            "400": 41.0,
            "500": 49.0,
            "600": 60.0,
            "700": 73.0,
            "800": 84.0,
            "900": 92.0,
            "950": 96.0,
        }
        target_l = light_anchor[key] / 100.0
        boosted_s = min(1.0, s * (1.05 if key in ("50", "100", "200") else 1.0))
        inverted[key] = _hsl_to_hex(h, boosted_s, target_l)
    return inverted


# ---------------------------------------------------------------------------
# WCAG contrast
# ---------------------------------------------------------------------------


def wcag_contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """W3C-canonical contrast ratio between two hex colours.

    Returns 1.0 (identical) to 21.0 (black ↔ white).
    """
    l1 = _relative_luminance(fg_hex)
    l2 = _relative_luminance(bg_hex)
    if l1 < l2:
        l1, l2 = l2, l1
    return round((l1 + 0.05) / (l2 + 0.05), 4)


def wcag_grade(
    ratio: float,
    *,
    large_text: bool = False,
) -> Literal["AAA", "AA", "AA_large", "FAIL"]:
    """Map a contrast ratio to a WCAG grade.

    * ``ratio >= 7``  → ``AAA``
    * ``ratio >= 4.5`` (normal) → ``AA``
    * ``ratio >= 3``  (large text) → ``AA_large``
    * otherwise       → ``FAIL``
    """
    if ratio >= 7.0:
        return "AAA"
    if ratio >= 4.5:
        return "AA"
    if large_text and ratio >= 3.0:
        return "AA_large"
    if ratio >= 3.0:
        return "AA_large"
    return "FAIL"


# ---------------------------------------------------------------------------
# Internal colour helpers (kept here so the import-scan test does not
# need to chase across modules to prove the in-process boundary).
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    v = (hex_value or "").strip()
    if v.startswith("#"):
        v = v[1:]
    if len(v) == 3:
        v = "".join(c + c for c in v)
    if len(v) != 6:
        return (0, 0, 0)
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02X}{g:02X}{b:02X}"


def _hex_to_hsl(hex_value: str) -> tuple[float, float, float]:
    r, g, b = _hex_to_rgb(hex_value)
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx = max(rf, gf, bf)
    mn = min(rf, gf, bf)
    l = (mx + mn) / 2.0
    if mx == mn:
        return (0.0, 0.0, l)
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == rf:
        h = (gf - bf) / d + (6.0 if gf < bf else 0.0)
    elif mx == gf:
        h = (bf - rf) / d + 2.0
    else:
        h = (rf - gf) / d + 4.0
    h *= 60.0
    return (h, s, l)


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    s = max(0.0, min(1.0, s))
    l = max(0.0, min(1.0, l))
    if s == 0.0:
        v = int(round(l * 255.0))
        return _rgb_to_hex(v, v, v)
    q = l * (1.0 + s) if l < 0.5 else l + s - l * s
    p = 2.0 * l - q

    def _hue_to_rgb(p_: float, q_: float, t: float) -> float:
        t = t % 1.0
        if t < 1.0 / 6.0:
            return p_ + (q_ - p_) * 6.0 * t
        if t < 1.0 / 2.0:
            return q_
        if t < 2.0 / 3.0:
            return p_ + (q_ - p_) * (2.0 / 3.0 - t) * 6.0
        return p_

    h_norm = (h / 360.0) % 1.0
    r = _hue_to_rgb(p, q, h_norm + 1.0 / 3.0) * 255.0
    g = _hue_to_rgb(p, q, h_norm) * 255.0
    b = _hue_to_rgb(p, q, h_norm - 1.0 / 3.0) * 255.0
    return _rgb_to_hex(int(round(r)), int(round(g)), int(round(b)))


def _relative_luminance(hex_value: str) -> float:
    r, g, b = _hex_to_rgb(hex_value)

    def _channel(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)
