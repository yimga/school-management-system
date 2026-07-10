"""Tests for services.theme_intelligence — in-process colour math (batch 1371, P1)."""

from __future__ import annotations

import ast
import struct
import zlib
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from services.theme_intelligence import (
    ExtractedColor,
    extract_dominant_colors_from_image,
    harmonize_for_dark,
    wcag_contrast_ratio,
    wcag_grade,
)


def _build_solid_png_16x16(rgb: tuple[int, int, int]) -> bytes:
    """Build a minimal 16x16 PNG with stdlib only (no Pillow).

    Format: signature + IHDR + IDAT (raw deflate of filter-0 rows) + IEND.
    """
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    width, height = 16, 16
    bit_depth = 8
    color_type = 2  # RGB
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)

    row = b"\x00" + bytes(rgb) * width  # filter byte + RGB pixels
    raw = row * height
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


class ExtractDominantColorsTests(SimpleTestCase):
    def test_extract_returns_at_least_one_color_from_solid_png(self):
        png_bytes = _build_solid_png_16x16((79, 70, 229))  # RMC indigo
        results = extract_dominant_colors_from_image(png_bytes)
        self.assertGreaterEqual(len(results), 1)
        for c in results:
            self.assertIsInstance(c, ExtractedColor)
            self.assertRegex(c.hex, r"^#[0-9A-F]{6}$")
            self.assertGreater(c.weight, 0.0)
            self.assertIn(c.source, ("pillow_quantize", "fallback"))

    def test_empty_bytes_returns_fallback(self):
        results = extract_dominant_colors_from_image(b"")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "fallback")
        self.assertEqual(results[0].hex, "#4F46E5")

    def test_url_string_returns_fallback_without_raising(self):
        # Regression: School.logo_url is a URLField, and callers passed the URL
        # string. It used to reach io.BytesIO(str) -> TypeError, logged as a
        # traceback on every day-1 palette resolution. A non-data-URI string must
        # now degrade to the fallback, never raise.
        results = extract_dominant_colors_from_image(
            "https://new-school.example.com/media/tenants/x/brand/logo.png"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "fallback")

    def test_base64_data_uri_string_is_decoded(self):
        import base64

        png = _build_solid_png_16x16((200, 10, 10))
        data_uri = "data:image/png;base64," + base64.b64encode(png).decode()
        results = extract_dominant_colors_from_image(data_uri)
        # Decoded successfully (no raise) and produced a real ExtractedColor.
        self.assertGreaterEqual(len(results), 1)
        self.assertIsInstance(results[0], ExtractedColor)
        self.assertRegex(results[0].hex, r"^#[0-9A-F]{6}$")
        self.assertIn(results[0].source, ("pillow_quantize", "fallback"))

    def test_fallback_when_pillow_unavailable(self):
        # Pillow import lives behind importlib.import_module("PIL.Image"), so
        # patching that surface simulates the no-Pillow path deterministically.
        png_bytes = _build_solid_png_16x16((79, 70, 229))

        def raise_import_error(name):  # pragma: no cover - patched
            if name == "PIL.Image":
                raise ImportError("simulated: Pillow not installed")
            import importlib as _imp

            return _imp.import_module(name)

        with patch(
            "services.theme_intelligence.importlib.import_module",
            side_effect=raise_import_error,
        ):
            results = extract_dominant_colors_from_image(png_bytes)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "fallback")


class WcagContrastTests(SimpleTestCase):
    def test_white_on_black_is_21(self):
        self.assertEqual(wcag_contrast_ratio("#FFFFFF", "#000000"), 21.0)

    def test_black_on_white_is_21(self):
        self.assertEqual(wcag_contrast_ratio("#000000", "#FFFFFF"), 21.0)

    def test_same_color_is_1(self):
        self.assertEqual(wcag_contrast_ratio("#888888", "#888888"), 1.0)

    def test_known_pair_indigo_on_white(self):
        # Sanity check — indigo on white is a high-contrast pair (~7-9).
        ratio = wcag_contrast_ratio("#4F46E5", "#FFFFFF")
        self.assertGreater(ratio, 5.0)

    def test_grade_AAA(self):
        self.assertEqual(wcag_grade(8.0), "AAA")

    def test_grade_AA(self):
        self.assertEqual(wcag_grade(5.0), "AA")

    def test_grade_AA_large(self):
        self.assertEqual(wcag_grade(3.5), "AA_large")

    def test_grade_FAIL(self):
        self.assertEqual(wcag_grade(2.0), "FAIL")


class HarmonizeForDarkTests(SimpleTestCase):
    def test_inverts_lightness_preserving_hue(self):
        light = {
            "50": "#F5F4FF",
            "100": "#E0DCFF",
            "200": "#C2BAFF",
            "300": "#9F95FF",
            "400": "#7B6CFF",
            "500": "#4F46E5",
            "600": "#3F38B7",
            "700": "#2F2A89",
            "800": "#1F1B5B",
            "900": "#0F0D2D",
            "950": "#070617",
        }
        dark = harmonize_for_dark(light)
        # Same keys
        self.assertEqual(set(dark.keys()), set(light.keys()))
        # In dark mode, "50" should be DARK (used as bg)
        self.assertLess(_lum(dark["50"]), _lum(light["50"]))
        # And "950" should be LIGHT (used as text on dark canvas)
        self.assertGreater(_lum(dark["950"]), _lum(light["950"]))

    def test_hue_preserved_within_tolerance(self):
        light = {
            "50": "#F5F4FF",
            "100": "#E0DCFF",
            "200": "#C2BAFF",
            "300": "#9F95FF",
            "400": "#7B6CFF",
            "500": "#4F46E5",
            "600": "#3F38B7",
            "700": "#2F2A89",
            "800": "#1F1B5B",
            "900": "#0F0D2D",
            "950": "#070617",
        }
        dark = harmonize_for_dark(light)
        # Check hue preservation for the 500 stop (the brand anchor).
        # We allow ±15° drift (loose for the inversion math).
        h_light = _hue(light["500"])
        h_dark_partner = _hue(dark["500"])
        # dark["500"] is derived from light["500"] partner (also 500), so
        # the hue should be near-identical.
        diff = min(abs(h_light - h_dark_partner), 360.0 - abs(h_light - h_dark_partner))
        self.assertLessEqual(diff, 15.0)

    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(harmonize_for_dark({}), {})


class ImportScanTests(SimpleTestCase):
    """ai_palette + theme_intelligence MUST be in-process: no httpx /
    requests / urllib / aiohttp imports."""

    FORBIDDEN = ("httpx", "requests", "urllib", "urllib3", "aiohttp")

    def _scan(self, module_relpath: str) -> list[str]:
        repo_root = Path(__file__).resolve().parents[2]
        source = (repo_root / module_relpath).read_text(encoding="utf-8")
        tree = ast.parse(source)
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    head = alias.name.split(".")[0]
                    if head in self.FORBIDDEN:
                        violations.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                head = module.split(".")[0]
                if head in self.FORBIDDEN:
                    violations.append(f"from {module}")
        return violations

    def test_ai_palette_no_network_imports(self):
        self.assertEqual(
            self._scan("services/ai_palette.py"),
            [],
            "services/ai_palette.py must be in-process only",
        )

    def test_theme_intelligence_no_network_imports(self):
        self.assertEqual(
            self._scan("services/theme_intelligence.py"),
            [],
            "services/theme_intelligence.py must be in-process only",
        )


# ---------------------------------------------------------------------------
# Helpers used by assertions (kept here, not imported from the module)
# ---------------------------------------------------------------------------


def _lum(hex_value: str) -> float:
    v = hex_value.lstrip("#")
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)

    def _c(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    return 0.2126 * _c(r) + 0.7152 * _c(g) + 0.0722 * _c(b)


def _hue(hex_value: str) -> float:
    v = hex_value.lstrip("#")
    r, g, b = int(v[0:2], 16) / 255.0, int(v[2:4], 16) / 255.0, int(v[4:6], 16) / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0.0
    d = mx - mn
    if mx == r:
        h = (g - b) / d + (6.0 if g < b else 0.0)
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return (h * 60.0) % 360.0
