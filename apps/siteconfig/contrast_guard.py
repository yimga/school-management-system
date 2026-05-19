"""
Contrast Auto-Guard: WCAG 4.5:1 minimum contrast for text on a given background.

Use for theme pack preview, dynamic UI, and stress-test assertions so cards, chips,
badges, and buttons never get unreadable text. Token-aligned defaults (#0f172a, #f1f5f9)
so guard output fits design-tokens.
"""

from __future__ import annotations


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Parse sRGB hex to (r, g, b) 0-255. Accepts #abc or #aabbcc."""
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(2 * c for c in value)
    if len(value) != 6:
        raise ValueError("Invalid hex length")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def luminance(rgb: tuple[int, int, int]) -> float:
    """Relative luminance per WCAG (sRGB linearized)."""

    def channel(c: int) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    """WCAG contrast ratio (1–21). Returns 0 on parse error."""
    try:
        lum1 = luminance(hex_to_rgb(hex1))
        lum2 = luminance(hex_to_rgb(hex2))
    except (ValueError, TypeError):
        return 0.0
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


# Token-aligned text colors (design-tokens / theme-visibility-guard)
DARK_TEXT = "#0f172a"
LIGHT_TEXT = "#f1f5f9"


def text_color_for_background(
    background_hex: str,
    min_ratio: float = 4.5,
    dark_option: str = DARK_TEXT,
    light_option: str = LIGHT_TEXT,
) -> str:
    """
    Return a text color (dark or light) that meets min_ratio against background.

    Use for theme pack preview and dynamic UI so text never fails contrast.
    Defaults use design-token–aligned values.
    """
    try:
        _ = luminance(hex_to_rgb(background_hex))
    except (ValueError, TypeError):
        return dark_option
    dark_ratio = contrast_ratio(background_hex, dark_option)
    light_ratio = contrast_ratio(background_hex, light_option)
    if dark_ratio >= min_ratio and dark_ratio >= light_ratio:
        return dark_option
    if light_ratio >= min_ratio:
        return light_option
    return dark_option if dark_ratio >= light_ratio else light_option


def meets_contrast(
    foreground_hex: str, background_hex: str, min_ratio: float = 4.5
) -> bool:
    """True if foreground on background meets WCAG min_ratio (e.g. 4.5:1)."""
    return contrast_ratio(foreground_hex, background_hex) >= min_ratio


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _rgb_to_hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (c / 255.0 for c in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d + (6 if g < b else 0)) / 6.0
    elif mx == g:
        h = ((b - r) / d + 2.0) / 6.0
    else:
        h = ((r - g) / d + 4.0) / 6.0
    return h % 1.0, s, l


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    if s == 0:
        v = int(round(l * 255))
        return v, v, v

    def hue_to_rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = hue_to_rgb(p, q, h + 1 / 3)
    g = hue_to_rgb(p, q, h)
    b = hue_to_rgb(p, q, h - 1 / 3)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def remediate_brand_hex_on_background(
    brand_hex: str,
    background_hex: str,
    *,
    min_ratio: float = 7.0,
    max_steps: int = 48,
) -> dict:
    """
    Shift brand hue/lightness (HSL) until foreground meets min_ratio on background.

    Preserves hue and saturation order; only adjusts lightness. Returns diagnostic
    payload for the theme customizer intercept UI.
    """
    brand_hex = (brand_hex or "").strip()
    background_hex = (background_hex or "").strip()
    if not brand_hex.startswith("#"):
        brand_hex = f"#{brand_hex}"
    if not background_hex.startswith("#"):
        background_hex = f"#{background_hex}"

    try:
        brand_rgb = hex_to_rgb(brand_hex)
        _ = hex_to_rgb(background_hex)
    except (ValueError, TypeError):
        return {
            "ok": False,
            "original_hex": brand_hex,
            "remediated_hex": brand_hex,
            "original_ratio": 0.0,
            "remediated_ratio": 0.0,
            "adjusted": False,
            "failure_line": "invalid_hex",
        }

    original_ratio = contrast_ratio(brand_hex, background_hex)
    if original_ratio >= min_ratio:
        return {
            "ok": True,
            "original_hex": brand_hex,
            "remediated_hex": brand_hex,
            "original_ratio": round(original_ratio, 2),
            "remediated_ratio": round(original_ratio, 2),
            "adjusted": False,
            "failure_line": None,
        }

    h, s, l = _rgb_to_hsl(brand_rgb)
    best_hex = brand_hex
    best_ratio = original_ratio
    # Search lightness toward readable pole (dark text on light bg → darken brand).
    bg_lum = luminance(hex_to_rgb(background_hex))
    toward_dark = bg_lum > 0.5
    step = -1.0 / max_steps if toward_dark else 1.0 / max_steps
    trial_l = l
    for _ in range(max_steps):
        trial_l = max(0.02, min(0.98, trial_l + step))
        trial_rgb = _hsl_to_rgb(h, s, trial_l)
        trial_hex = _rgb_to_hex(trial_rgb)
        ratio = contrast_ratio(trial_hex, background_hex)
        if ratio > best_ratio:
            best_ratio = ratio
            best_hex = trial_hex
        if ratio >= min_ratio:
            return {
                "ok": True,
                "original_hex": brand_hex,
                "remediated_hex": trial_hex,
                "original_ratio": round(original_ratio, 2),
                "remediated_ratio": round(ratio, 2),
                "adjusted": True,
                "failure_line": "primary_on_surface",
            }

    return {
        "ok": best_ratio >= min_ratio,
        "original_hex": brand_hex,
        "remediated_hex": best_hex,
        "original_ratio": round(original_ratio, 2),
        "remediated_ratio": round(best_ratio, 2),
        "adjusted": best_hex != brand_hex,
        "failure_line": "primary_on_surface",
    }
