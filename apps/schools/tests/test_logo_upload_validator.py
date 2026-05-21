"""Tests for the Day-1 LogoUploadValidator + extract_brand_seed_from_logo."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.schools.school_brand_assets import (
    DAY1_LOGO_MAX_BYTES,
    LogoUploadValidator,
    extract_brand_seed_from_logo,
)


# Realistic-shape minimal magic-byte payloads — enough for the sniffer to
# identify the format without having to ship real images in the tree.
_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
_JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 24
_WEBP_HEADER = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
_SVG_PAYLOAD = b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>"
_GIF_HEADER = b"GIF89a" + b"\x00" * 26


class LogoUploadValidatorTests(SimpleTestCase):
    def test_png_happy_path(self):
        ok, info = LogoUploadValidator(_PNG_HEADER)
        self.assertTrue(ok)
        self.assertEqual(info, "image/png")

    def test_jpeg_happy_path(self):
        ok, info = LogoUploadValidator(_JPEG_HEADER)
        self.assertTrue(ok)
        self.assertEqual(info, "image/jpeg")

    def test_webp_happy_path(self):
        ok, info = LogoUploadValidator(_WEBP_HEADER)
        self.assertTrue(ok)
        self.assertEqual(info, "image/webp")

    def test_svg_is_rejected(self):
        ok, info = LogoUploadValidator(_SVG_PAYLOAD)
        self.assertFalse(ok)
        self.assertIn("SVG", info)

    def test_gif_is_rejected(self):
        ok, info = LogoUploadValidator(_GIF_HEADER)
        self.assertFalse(ok)
        self.assertIn("PNG", info)  # error names allowed formats

    def test_empty_upload_rejected(self):
        ok, info = LogoUploadValidator(b"")
        self.assertFalse(ok)
        self.assertEqual(info, "empty upload")

    def test_none_upload_rejected(self):
        ok, info = LogoUploadValidator(None)  # type: ignore[arg-type]
        self.assertFalse(ok)

    def test_oversize_upload_rejected(self):
        # PNG header followed by enough zeros to push past the 1.5 MB cap.
        big = _PNG_HEADER + b"\x00" * (DAY1_LOGO_MAX_BYTES + 1)
        ok, info = LogoUploadValidator(big)
        self.assertFalse(ok)
        self.assertIn("cap", info)

    def test_malicious_svg_renamed_as_png_still_rejected(self):
        """A maliciously-renamed SVG must be caught by the magic-byte sniff."""
        ok, info = LogoUploadValidator(_SVG_PAYLOAD)
        self.assertFalse(ok)

    def test_non_bytes_type_rejected(self):
        ok, info = LogoUploadValidator("not bytes")  # type: ignore[arg-type]
        self.assertFalse(ok)
        self.assertIn("bytes", info)


class ExtractBrandSeedFromLogoTests(SimpleTestCase):
    def test_returns_none_when_no_logo_url(self):
        school = mock.MagicMock(logo_url="")
        self.assertIsNone(extract_brand_seed_from_logo(school))

    def test_returns_none_when_module_unavailable(self):
        school = mock.MagicMock(logo_url="https://example.test/logo.png")
        # Force ImportError.
        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def _imp(name, *args, **kwargs):
            if name == "services.theme_intelligence":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=_imp):
            self.assertIsNone(extract_brand_seed_from_logo(school))

    def test_returns_hex_when_module_provides_one(self):
        school = mock.MagicMock(logo_url="https://example.test/logo.png")
        fake_module = mock.MagicMock()
        fake_module.extract_dominant_colors_from_image.return_value = "#abcdef"
        with mock.patch.dict(
            "sys.modules", {"services.theme_intelligence": fake_module}
        ):
            self.assertEqual(extract_brand_seed_from_logo(school), "#abcdef")
