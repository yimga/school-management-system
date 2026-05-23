"""Tests for ExperienceTemplate registry + overlay + LocalExperienceProfile invariants."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.brand_experience import experience_templates as et
from apps.brand_experience.template_ai_recommender import (
    TemplateRecommendation,
    recommend_local_first_for_country,
)
from apps.platform_runtime import pack_contract as pc
from apps.siteconfig import local_experience_profiles as lep


class ExperienceTemplateRegistryTests(SimpleTestCase):
    def test_exactly_75_overlays_registered(self):
        self.assertEqual(len(et.OVERLAYS), 75)

    def test_overlay_keys_unique(self):
        keys = [o.key for o in et.OVERLAYS]
        self.assertEqual(len(set(keys)), len(keys))

    def test_every_overlay_has_matching_pack_contract(self):
        pack_keys = {p.key for p in pc.EXPERIENCE_TEMPLATE_PACKS}
        overlay_keys = {o.key for o in et.OVERLAYS}
        self.assertEqual(pack_keys, overlay_keys)

    def test_assert_registry_invariants_passes(self):
        et.assert_registry_invariants()

    def test_category_distribution_matches_plan(self):
        counts = {}
        for o in et.OVERLAYS:
            counts[o.category] = counts.get(o.category, 0) + 1
        self.assertEqual(counts.get("operator"), 10)
        self.assertEqual(counts.get("tenant-admin"), 8)
        self.assertEqual(counts.get("teacher"), 8)
        self.assertEqual(counts.get("parent"), 6)
        self.assertEqual(counts.get("student"), 6)
        self.assertEqual(counts.get("staff"), 4)
        self.assertEqual(counts.get("specialized"), 8)
        self.assertEqual(counts.get("local-first"), 25)

    def test_layout_family_in_1_to_10(self):
        for o in et.OVERLAYS:
            self.assertIn(o.layout_family, et.LAYOUT_FAMILY_NAMES.keys())

    def test_palette_family_registered(self):
        for o in et.OVERLAYS:
            self.assertIn(o.palette_family, et.PALETTE_FAMILIES)

    def test_accessibility_floor_AA(self):
        for o in et.OVERLAYS:
            self.assertIn(o.accessibility_level, {"AA", "AAA"})

    def test_local_first_templates_reference_real_profiles(self):
        profile_keys = set(lep.profile_keys())
        for o in et.OVERLAYS:
            if o.category == "local-first":
                self.assertTrue(o.local_profile_ref, f"{o.key}: missing local_profile_ref")
                self.assertIn(o.local_profile_ref, profile_keys, f"{o.key}: ref {o.local_profile_ref} not in profile registry")


class TenantBoundaryTests(SimpleTestCase):
    def test_operator_templates_have_tenant_safe_false(self):
        pack_by_key = {p.key: p for p in pc.EXPERIENCE_TEMPLATE_PACKS}
        for o in et.OVERLAYS:
            pack = pack_by_key[o.key]
            if o.category == "operator":
                self.assertFalse(pack.tenant_safe, f"{o.key}: operator template must be tenant_safe=False")
                self.assertTrue(pack.platform_only, f"{o.key}: operator template must be platform_only=True")

    def test_tenant_safe_filter_hides_operator_templates(self):
        tenant_rows = pc.list_packs(pack_type="experience_template", tenant_safe_only=True)
        tenant_keys = {row["key"] for row in tenant_rows}
        operator_keys = {o.key for o in et.OVERLAYS if o.category == "operator"}
        leaked = operator_keys & tenant_keys
        self.assertEqual(leaked, set())

    def test_list_overlays_filter_respects_tenant_safe_only(self):
        all_rows = et.list_overlays()
        tenant_rows = et.list_overlays(tenant_safe_only=True)
        self.assertGreater(len(all_rows), len(tenant_rows))
        operator_keys = {o.key for o in et.OVERLAYS if o.category == "operator"}
        for row in tenant_rows:
            self.assertNotIn(row["key"], operator_keys)


class LocalExperienceProfileTests(SimpleTestCase):
    def test_exactly_25_profiles(self):
        self.assertEqual(len(lep.PROFILES), 25)

    def test_profile_keys_unique(self):
        keys = [p.key for p in lep.PROFILES]
        self.assertEqual(len(set(keys)), len(keys))

    def test_assert_registry_invariants_passes(self):
        lep.assert_registry_invariants()

    def test_countries_are_iso2_uppercase(self):
        for p in lep.PROFILES:
            self.assertEqual(len(p.country), 2)
            self.assertEqual(p.country, p.country.upper())

    def test_languages_non_empty(self):
        for p in lep.PROFILES:
            self.assertTrue(p.languages, f"{p.key}: languages must be non-empty")

    def test_currency_is_iso4217(self):
        for p in lep.PROFILES:
            self.assertEqual(len(p.currency_default), 3)


class TemplateAIRecommenderTests(SimpleTestCase):
    def test_recommend_local_first_for_country_returns_only_local_first(self):
        rows = recommend_local_first_for_country("IN")
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(row["category"], "local-first")
            self.assertIn("IN", row["supported_countries"])

    def test_recommend_local_first_unknown_country_returns_empty(self):
        rows = recommend_local_first_for_country("ZZ")
        self.assertEqual(rows, [])

    def test_template_recommendation_is_frozen(self):
        rec = TemplateRecommendation(
            primary="parent-family-home",
            why="test",
            required_modules=(),
            missing_setup=(),
            preview_url="/x/",
            risks=(),
            alternatives=(),
            confidence=0.5,
            source="rules",
        )
        with self.assertRaises(AttributeError):
            rec.confidence = 1.0  # type: ignore[misc]
