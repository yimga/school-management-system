"""Coverage for the SVG sanitizer that gates tenant brand uploads."""

from __future__ import annotations

import io
import unittest

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.siteconfig.svg_sanitize import sanitize_svg_bytes, validate_svg_safe


CLEAN_SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="#4f46e5"/><text x="50%" y="55%" text-anchor="middle" font-size="20" fill="#fff">R</text></svg>'


class SanitizeSVGBytesTests(unittest.TestCase):
    def test_clean_svg_round_trips(self):
        out = sanitize_svg_bytes(CLEAN_SVG)
        self.assertIn(b"<svg", out)
        self.assertIn(b"circle", out)
        self.assertIn(b"R", out)

    def test_script_tag_is_stripped(self):
        evil = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<script>alert(1)</script>'
            b'<circle r="10"/></svg>'
        )
        out = sanitize_svg_bytes(evil)
        self.assertNotIn(b"<script", out.lower())
        self.assertNotIn(b"alert", out)
        self.assertIn(b"circle", out)

    def test_onload_handler_stripped(self):
        evil = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><circle r="10"/></svg>'
        out = sanitize_svg_bytes(evil)
        self.assertNotIn(b"onload", out.lower())
        self.assertNotIn(b"alert", out)

    def test_foreign_object_stripped(self):
        evil = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<foreignObject><iframe src="javascript:alert(1)"/></foreignObject>'
            b'<circle r="10"/></svg>'
        )
        out = sanitize_svg_bytes(evil)
        self.assertNotIn(b"foreignObject", out)
        self.assertNotIn(b"iframe", out)
        self.assertNotIn(b"javascript", out)

    def test_external_href_stripped(self):
        evil = (
            b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
            b'<use xlink:href="https://evil.example/payload.svg#x"/></svg>'
        )
        out = sanitize_svg_bytes(evil)
        # The <use> element with external href is dropped entirely.
        self.assertNotIn(b"evil.example", out)

    def test_internal_use_fragment_survives(self):
        clean = (
            b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
            b'<defs><circle id="dot" r="2"/></defs>'
            b'<use xlink:href="#dot"/></svg>'
        )
        out = sanitize_svg_bytes(clean)
        self.assertIn(b"use", out)

    def test_doctype_rejected(self):
        evil = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<svg xmlns="http://www.w3.org/2000/svg">&xxe;</svg>'
        )
        with self.assertRaises(ValidationError):
            sanitize_svg_bytes(evil)

    def test_entity_decl_rejected(self):
        evil = (
            b'<svg xmlns="http://www.w3.org/2000/svg"><!ENTITY x "boom"/></svg>'
        )
        with self.assertRaises(ValidationError):
            sanitize_svg_bytes(evil)

    def test_non_svg_rejected(self):
        with self.assertRaises(ValidationError):
            sanitize_svg_bytes(b"<html><body>not an svg</body></html>")

    def test_empty_rejected(self):
        with self.assertRaises(ValidationError):
            sanitize_svg_bytes(b"")


class ValidateSVGSafeTests(unittest.TestCase):
    def test_raster_files_pass_through_untouched(self):
        png = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\nfake", content_type="image/png")
        # Should not raise; raster path is a no-op.
        validate_svg_safe(png)
        png.seek(0)
        self.assertEqual(png.read(4), b"\x89PNG")

    def test_clean_svg_upload_passes(self):
        upload = SimpleUploadedFile("logo.svg", CLEAN_SVG, content_type="image/svg+xml")
        validate_svg_safe(upload)

    def test_malicious_svg_upload_rejected(self):
        evil = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        )
        upload = SimpleUploadedFile("evil.svg", evil, content_type="image/svg+xml")
        with self.assertRaises(ValidationError):
            validate_svg_safe(upload)

    def test_too_large_svg_rejected(self):
        oversized = b'<svg xmlns="http://www.w3.org/2000/svg"/>' + (b" " * (1024 * 1024 + 10))
        upload = SimpleUploadedFile("big.svg", oversized, content_type="image/svg+xml")
        with self.assertRaises(ValidationError):
            validate_svg_safe(upload)


if __name__ == "__main__":
    unittest.main()
