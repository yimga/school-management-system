"""Platform-wide AAA brand guard on save and render paths."""

from django.test import TestCase

from apps.siteconfig.brand_guard_runtime import (
    guard_brand_dict,
    guard_brand_hex_fields,
)
from apps.siteconfig.contrast_guard import contrast_ratio
class BrandGuardRuntimeTests(TestCase):
    def test_guard_brand_dict_shifts_yellow_on_white(self):
        brand, adjusted = guard_brand_dict(
            {"primary_color": "#ffff00", "accent_color": "#198754"}
        )
        self.assertTrue(adjusted or contrast_ratio(brand["primary_color"], "#ffffff") >= 7.0)

    def test_guard_brand_hex_fields_on_instance(self):
        class _Brand:
            primary_color = "#ffff00"

        brand = _Brand()
        guard_brand_hex_fields(brand, min_ratio=7.0)
        self.assertGreaterEqual(contrast_ratio(brand.primary_color, "#ffffff"), 7.0)

    def test_guard_meets_aaa_on_light_surface(self):
        class _Brand:
            primary_color = "#ffff00"
            accent_color = "#00ff00"

        brand = _Brand()
        guard_brand_hex_fields(brand, min_ratio=7.0)
        self.assertGreaterEqual(contrast_ratio(brand.primary_color, "#ffffff"), 7.0)
