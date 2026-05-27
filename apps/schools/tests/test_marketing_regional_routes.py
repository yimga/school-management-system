"""Regional marketing URL wiring (legacy + canonical)."""
from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import reverse

from apps.schools.marketing_region import (
    MARKETING_LEGACY_REGIONAL_SHORTCUTS,
    regional_landing_path,
)


class MarketingRegionalRoutesTests(SimpleTestCase):
    def test_top_ten_canonical_paths(self):
        for cc in ("US", "GB", "CA", "SA", "AE", "NG", "KE", "IN", "BR", "ID"):
            self.assertTrue(regional_landing_path(cc).startswith("/"))

    def test_legacy_shortcuts_reverse(self):
        for _prefix, country, _lang, url_name in MARKETING_LEGACY_REGIONAL_SHORTCUTS:
            path = reverse(url_name)
            self.assertTrue(path.endswith("/"))

    def test_canonical_region_reverse(self):
        path = reverse("marketing_region", kwargs={"language_code": "en", "country_code": "us"})
        self.assertIn("/en/us/", path)
