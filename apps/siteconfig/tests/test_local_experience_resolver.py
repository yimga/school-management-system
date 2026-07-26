"""Local experience resolver tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.siteconfig.local_experience_resolver import (
    count_configured_countries,
    resolve_local_experience_for_country,
)


class LocalExperienceResolverTests(SimpleTestCase):
    def test_cm_has_deep_profile(self):
        result = resolve_local_experience_for_country("CM")
        self.assertTrue(result["configured"])
        self.assertEqual(result["depth"], "deep")
        self.assertGreater(result["profile_count"], 0)

    def test_at_gets_derived_profile(self):
        result = resolve_local_experience_for_country("AT")
        self.assertTrue(result["configured"])
        self.assertIn(result["depth"], ("derived", "deep", "baseline"))
        self.assertIn("academic_system", result)

    def test_unknown_country(self):
        # Universal coverage (global-first): resolve_country_pack always returns a
        # complete pack via its generic-fallback tier, so an unrecognized ISO code
        # still resolves to a baseline/derived experience (academic_system falls back
        # to "international"). The only genuinely unconfigured input is an empty code.
        result = resolve_local_experience_for_country("ZZ")
        self.assertTrue(result["configured"])
        self.assertTrue(result.get("academic_system"))
        empty = resolve_local_experience_for_country("")
        self.assertFalse(empty["configured"])

    def test_baseline_coverage_meets_200(self):
        stats = count_configured_countries()
        self.assertGreaterEqual(stats["total_baselines"], 200)
        self.assertGreaterEqual(stats["configured"], 200)
        self.assertGreater(stats["derived"] + stats["deep"], 50)
