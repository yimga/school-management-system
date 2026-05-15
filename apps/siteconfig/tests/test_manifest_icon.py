"""Coverage for the per-tenant PWA icon endpoint (v2.60 Tier 1 closure).

Locks in the contract that ``/manifest/icon-<size>.png`` returns a PNG of
the requested size, that the maskable variant tints the canvas with the
tenant primary, and that unsupported sizes are refused (DoS guard).
"""

from __future__ import annotations

import io
import unittest

from django.core.exceptions import ValidationError
from django.test import RequestFactory

from apps.siteconfig.views_manifest_icon import (
    _ALLOWED_SIZES,
    icon_any,
    icon_maskable,
    manifest_icon_view,
)


class _StubSettings:
    """Mimic the duck-typed effective settings object used by the view."""

    def __init__(self, primary_color="#4f46e5", background_color="#fafafa",
                 site_name="Test School", logo=None):
        self.primary_color = primary_color
        self.background_color = background_color
        self.site_name = site_name
        self.logo = logo


class ManifestIconRouteTests(unittest.TestCase):
    """End-to-end tests for the URL handlers."""

    def setUp(self):
        self.factory = RequestFactory()

    def _patch_settings(self, settings_obj):
        from apps.siteconfig import views_manifest_icon

        self._orig = views_manifest_icon._resolve_effective_settings
        views_manifest_icon._resolve_effective_settings = (
            lambda request: settings_obj
        )

    def tearDown(self):
        from apps.siteconfig import views_manifest_icon

        if hasattr(self, "_orig"):
            views_manifest_icon._resolve_effective_settings = self._orig

    def test_rejects_unsupported_size(self):
        request = self.factory.get("/manifest/icon-100.png")
        response = icon_any(request, size=100)
        self.assertEqual(response.status_code, 400)

    def test_accepts_192_and_returns_png(self):
        self._patch_settings(_StubSettings())
        request = self.factory.get("/manifest/icon-192.png")
        response = icon_any(request, size=192)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("Vary", response.headers)
        self.assertIn("Host", response["Vary"])
        # PNG magic bytes.
        self.assertEqual(response.content[:8], b"\x89PNG\r\n\x1a\n")

    def test_512_size_produces_512px_png(self):
        from PIL import Image

        self._patch_settings(_StubSettings())
        request = self.factory.get("/manifest/icon-512.png")
        response = icon_any(request, size=512)
        self.assertEqual(response.status_code, 200)
        img = Image.open(io.BytesIO(response.content))
        self.assertEqual(img.size, (512, 512))

    def test_maskable_variant_fills_canvas_with_primary(self):
        from PIL import Image

        self._patch_settings(_StubSettings(primary_color="#ff00ff"))
        request = self.factory.get("/manifest/icon-192-maskable.png")
        response = icon_maskable(request, size=192)
        self.assertEqual(response.status_code, 200)
        img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        # Corner pixel should be the primary color (maskable fills bg).
        corner = img.getpixel((0, 0))
        self.assertEqual(corner[:3], (255, 0, 255))

    def test_monogram_uses_first_letter_of_site_name(self):
        """No logo on file → renders monogram. We can't OCR the glyph but
        we can confirm the response is a valid PNG of the right size."""
        from PIL import Image

        self._patch_settings(_StubSettings(site_name="Acme Academy"))
        request = self.factory.get("/manifest/icon-192.png")
        response = icon_any(request, size=192)
        img = Image.open(io.BytesIO(response.content))
        self.assertEqual(img.size, (192, 192))

    def test_allowed_sizes_includes_spec_minimums(self):
        # PWA install spec requires 192 + 512.
        self.assertIn(192, _ALLOWED_SIZES)
        self.assertIn(512, _ALLOWED_SIZES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
