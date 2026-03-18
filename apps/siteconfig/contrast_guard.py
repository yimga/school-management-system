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
