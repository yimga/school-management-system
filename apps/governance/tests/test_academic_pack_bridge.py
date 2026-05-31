"""Tests for academic pack bridge (global kernel Phase 0–1)."""

from django.test import SimpleTestCase

from apps.governance.academic_pack_bridge import (
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

    def test_resolve_grading_preset_cameroon(self):
        self.assertEqual(resolve_grading_preset_key("CM"), "west_african_waec")

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
