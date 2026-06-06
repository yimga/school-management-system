"""Multi-language signup selection helpers (v4.02.51)."""

from django.test import SimpleTestCase

from apps.siteconfig.country_localization_service import (
    parse_signup_language_selection,
    resolve_primary_language_code,
)


class SignupMultilingualSelectionTests(SimpleTestCase):
    def test_single_language_defaults_to_only_code(self):
        codes, primary = parse_signup_language_selection(
            country_code="CM",
            language_codes=["fr"],
        )
        self.assertEqual(codes, ["fr"])
        self.assertEqual(primary, "fr")

    def test_multi_language_preserves_all_valid_codes(self):
        codes, primary = parse_signup_language_selection(
            country_code="CA",
            language_codes=["fr", "en"],
        )
        self.assertEqual(codes, ["fr", "en"])
        self.assertIn(primary, codes)

    def test_india_state_stars_regional_primary(self):
        primary = resolve_primary_language_code(
            "IN",
            ["hi", "en", "ta"],
            state_code="IN-TN",
        )
        self.assertEqual(primary, "ta")

    def test_legacy_single_language_code_fallback(self):
        codes, primary = parse_signup_language_selection(
            country_code="BE",
            language_code_legacy="nl",
        )
        self.assertEqual(codes, ["nl"])
        self.assertEqual(primary, "nl")

    def test_explicit_primary_wins_when_selected(self):
        codes, primary = parse_signup_language_selection(
            country_code="CA",
            language_codes=["en", "fr"],
            primary_language_code="fr",
        )
        self.assertEqual(codes, ["en", "fr"])
        self.assertEqual(primary, "fr")
