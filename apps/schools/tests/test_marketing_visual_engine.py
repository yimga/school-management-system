"""Tests for VISUAL-ENGINE-10X marketing media + sandbox API."""
from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.schools.marketing_geo_context import build_geo_context
from apps.schools.marketing_media_matrix import (
    assets_for_country,
    loop_bucket_for_country,
)
from apps.schools.views_marketing_api import _validate_sandbox_payload


class MarketingMediaMatrixTests(SimpleTestCase):
    def test_loop_bucket_top_markets(self):
        self.assertEqual(loop_bucket_for_country("US"), "sovereign_us")
        self.assertEqual(loop_bucket_for_country("NG"), "sovereign_ssa")
        self.assertEqual(loop_bucket_for_country("XX"), "sovereign_default")

    def test_assets_include_loop_paths(self):
        assets = assets_for_country("IN")
        self.assertIn("sovereign_hero_loop_mp4", assets)
        self.assertTrue(assets["sovereign_hero_loop_mp4"].endswith(".mp4"))


class SandboxValidateTests(SimpleTestCase):
    def test_valid_payload(self):
        ok, msg, steps = _validate_sandbox_payload(
            {"region": "US", "school_size": "medium", "modules": ["finance", "starter_stack"]}
        )
        self.assertTrue(ok)
        self.assertIn("starter_stack", steps)

    def test_invalid_region(self):
        ok, _, _ = _validate_sandbox_payload(
            {"region": "USA", "school_size": "medium", "modules": ["finance"]}
        )
        self.assertFalse(ok)


class MarketingGeoContextTests(SimpleTestCase):
    def test_build_geo_context_defaults(self):
        factory = RequestFactory()
        request = factory.get("/")
        geo = build_geo_context(request)
        self.assertIn("country_code", geo)
        self.assertIn("direction", geo)
        self.assertIn("apm_icons", geo)
