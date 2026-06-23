"""Tests for academic pack bridge (global kernel Phase 0–1)."""

from django.test import SimpleTestCase

from apps.governance.academic_pack_bridge import (
    _COUNTRY_GRADING_PRESET,
    _FRANCOPHONE_BAC_COUNTRIES,
    audit_pack_matrix_alignment,
    pack_source_tier,
    resolve_academic_pack_context,
    resolve_grading_preset_key,
)


class AcademicPackBridgeTests(SimpleTestCase):
    def test_pack_source_tier_native(self):
        self.assertEqual(pack_source_tier("country:CM"), "tier1_native")

    def test_pack_source_tier_regional(self):
        self.assertEqual(pack_source_tier("regional:africa-francophone"), "tier1_regional_clone")

    def test_pack_source_tier_generic(self):
        self.assertEqual(pack_source_tier("regional:generic"), "generic_fallback")

    def test_resolve_grading_preset_cameroon_is_francophone_bac(self):
        # Cameroon (home market, francophone-majority) uses the 0-20 Bac scale.
        # The curated override corrects the old coarse africa->percentage bucket
        # that mis-assigned the entire francophone world to west_african_waec.
        self.assertEqual(resolve_grading_preset_key("CM"), "francophone_bac")

    def test_resolve_grading_preset_france_is_francophone_bac(self):
        # France resolved to british_igcse via the europe bucket before the
        # curated override (the fine-grained europe-romance key was dead code).
        self.assertEqual(resolve_grading_preset_key("FR"), "francophone_bac")

    def test_francophone_bac_countries_all_resolve_to_bac(self):
        for cc in _FRANCOPHONE_BAC_COUNTRIES:
            self.assertEqual(
                resolve_grading_preset_key(cc), "francophone_bac", cc
            )

    def test_country_override_map_only_maps_known_presets(self):
        known = {
            "francophone_bac", "west_african_waec", "british_igcse",
            "american", "east_asia_competitive",
        }
        for cc, preset in _COUNTRY_GRADING_PRESET.items():
            self.assertIn(preset, known, cc)

    def test_non_overridden_country_keeps_bucket_fallback(self):
        # Nigeria is not in the override map -> africa bucket -> WASSCE.
        self.assertEqual(resolve_grading_preset_key("NG"), "west_african_waec")
        # The US keeps GPA via the americas bucket.
        self.assertEqual(resolve_grading_preset_key("US"), "american")

    def test_resolve_grading_preset_handles_blank_and_lowercase(self):
        self.assertEqual(resolve_grading_preset_key("fr"), "francophone_bac")
        # Blank / junk never raises and falls to the generic default.
        self.assertEqual(resolve_grading_preset_key(""), "american")
        self.assertEqual(resolve_grading_preset_key(None), "american")

    def test_resolve_academic_pack_context_has_school_types(self):
        ctx = resolve_academic_pack_context("CM")
        self.assertEqual(ctx.get("iso_alpha2"), "CM")
        self.assertTrue(ctx.get("school_types"))
        self.assertTrue(ctx.get("grading_preset_key"))

    def test_audit_alignment_empty_rows(self):
        self.assertEqual(audit_pack_matrix_alignment([]), [])

    def test_latam_supports_multi_shift(self):
        ctx = resolve_academic_pack_context("MX")
        self.assertTrue(ctx.get("supports_multi_shift"))
