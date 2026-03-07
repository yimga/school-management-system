"""
Tests for contrast_guard: WCAG 4.5:1 text color for background, contrast ratio, meets_contrast.
Run with: python manage.py test apps.siteconfig.tests.test_contrast_guard -v 1
"""
from django.test import SimpleTestCase

from apps.siteconfig.contrast_guard import (
    contrast_ratio,
    hex_to_rgb,
    luminance,
    meets_contrast,
    text_color_for_background,
    DARK_TEXT,
    LIGHT_TEXT,
)


class ContrastGuardTests(SimpleTestCase):
    """Contrast Auto-Guard utility tests."""

    def test_hex_to_rgb_full(self):
        self.assertEqual(hex_to_rgb("#ffffff"), (255, 255, 255))
        self.assertEqual(hex_to_rgb("0f172a"), (15, 23, 42))

    def test_hex_to_rgb_short(self):
        self.assertEqual(hex_to_rgb("#fff"), (255, 255, 255))

    def test_hex_to_rgb_invalid_raises(self):
        with self.assertRaises(ValueError):
            hex_to_rgb("ab")
        with self.assertRaises(ValueError):
            hex_to_rgb("#abcd")

    def test_luminance_white(self):
        self.assertAlmostEqual(luminance((255, 255, 255)), 1.0, places=5)

    def test_luminance_black(self):
        self.assertAlmostEqual(luminance((0, 0, 0)), 0.0, places=5)

    def test_contrast_ratio_white_on_black(self):
        self.assertGreaterEqual(contrast_ratio("#ffffff", "#000000"), 21.0)

    def test_contrast_ratio_black_on_white(self):
        self.assertGreaterEqual(contrast_ratio("#000000", "#ffffff"), 21.0)

    def test_contrast_ratio_same(self):
        self.assertEqual(contrast_ratio("#888888", "#888888"), 1.0)

    def test_contrast_ratio_wcag_45(self):
        # #0f172a on #f1f5f9 should meet 4.5:1
        r = contrast_ratio(DARK_TEXT, "#f1f5f9")
        self.assertGreaterEqual(r, 4.5, msg=f"Dark text on light bg ratio {r}")
        r = contrast_ratio(LIGHT_TEXT, "#1e293b")
        self.assertGreaterEqual(r, 4.5, msg=f"Light text on dark bg ratio {r}")

    def test_text_color_for_background_white_returns_dark(self):
        out = text_color_for_background("#ffffff")
        self.assertEqual(out, DARK_TEXT)

    def test_text_color_for_background_black_returns_light(self):
        out = text_color_for_background("#0f172a")
        self.assertEqual(out, LIGHT_TEXT)

    def test_text_color_for_background_meets_ratio(self):
        for bg in ("#ffffff", "#f8fafc", "#1e293b", "#0f172a", "#3b82f6", "#94a3b8"):
            with self.subTest(bg=bg):
                text = text_color_for_background(bg)
                ratio = contrast_ratio(text, bg)
                self.assertGreaterEqual(
                    ratio, 4.5,
                    msg=f"text_color_for_background({bg}) -> {text} ratio {ratio}",
                )

    def test_meets_contrast_true(self):
        self.assertTrue(meets_contrast("#0f172a", "#f1f5f9", 4.5))
        self.assertTrue(meets_contrast("#f1f5f9", "#1e293b", 4.5))

    def test_meets_contrast_false(self):
        self.assertFalse(meets_contrast("#cccccc", "#eeeeee", 4.5))
