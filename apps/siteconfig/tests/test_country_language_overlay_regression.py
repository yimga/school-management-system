"""Regression: Tier-1 country patches must not wipe Wave 6 language overlays."""

from django.test import SimpleTestCase

from apps.siteconfig.country_localization_service import get_languages

_AFFECTED = ("CM", "GH", "KE", "SN", "CI", "TZ", "UG", "RW", "ET", "EG", "ZA")


class CountryLanguageOverlayRegressionTests(SimpleTestCase):
    def test_multilingual_african_tier1_countries_have_languages(self):
        for code in _AFFECTED:
            with self.subTest(country=code):
                langs = get_languages(code)
                self.assertGreater(
                    len(langs),
                    0,
                    f"{code} must expose at least one language for signup",
                )

    def test_cameroon_has_bilingual_overlay(self):
        codes = {str(item.get("code") or "").lower() for item in get_languages("CM")}
        self.assertIn("fr", codes)
        self.assertIn("en", codes)
