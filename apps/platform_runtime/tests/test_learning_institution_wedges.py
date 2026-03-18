"""SOT wedges 23–30 / 31–43: catalog completeness + runtime apply."""

from django.test import TestCase

from apps.platform_runtime.learning_institution_catalog import (
    INSTITUTION_TYPE_PACKS,
    INSTITUTION_CODE_ALIASES,
    LEARNING_DELIVERY_MODES,
    delivery_wedges,
    institution_wedges,
    normalize_delivery_code,
    normalize_institution_code,
)
from apps.platform_runtime.learning_institution_runtime import (
    apply_learning_institution_packs,
)
from apps.schools.models import School


class LearningInstitutionWedgeCatalogTests(TestCase):
    def test_delivery_exactly_eight_wedges_23_to_30(self):
        self.assertEqual(len(LEARNING_DELIVERY_MODES), 8)
        self.assertEqual(delivery_wedges(), list(range(23, 31)))
        codes = {m["code"] for m in LEARNING_DELIVERY_MODES}
        self.assertIn("W23_IN_PERSON", codes)
        self.assertIn("W30_COHORT_BASED", codes)

    def test_institution_exactly_thirteen_wedges_31_to_43(self):
        self.assertEqual(len(INSTITUTION_TYPE_PACKS), 13)
        self.assertEqual(institution_wedges(), list(range(31, 44)))

    def test_legacy_aliases_normalize(self):
        self.assertEqual(normalize_delivery_code("FACE_TO_FACE"), "W23_IN_PERSON")
        self.assertEqual(normalize_institution_code("GENERAL_K12"), "W31_GENERAL_K12")
        self.assertEqual(
            normalize_institution_code("HIGHER_ED"), "W43_HIGHER_EDUCATION"
        )

    def test_all_legacy_institution_codes_map(self):
        for legacy in INSTITUTION_CODE_ALIASES:
            self.assertTrue(normalize_institution_code(legacy).startswith("W"))


class ApplyLearningInstitutionRuntimeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Wedge Test School",
            slug="wedge-test",
            subdomain="wedge-test",
            is_active=True,
        )

    def test_apply_sets_wedges_and_features(self):
        apply_learning_institution_packs(
            self.school,
            delivery_mode_codes=["W25_HYBRID", "W29_SELF_PACED"],
            institution_type_code="W32_TVET",
        )
        self.school.refresh_from_db()
        s = self.school.settings
        self.assertEqual(set(s.get("learning_delivery_wedges") or []), {25, 29})
        self.assertEqual(s.get("institution_type_wedge"), 32)
        self.assertEqual(s.get("institution_type_pack"), "W32_TVET")
        self.assertIn("tvet", self.school.features)

    def test_apply_legacy_codes(self):
        apply_learning_institution_packs(
            self.school,
            delivery_mode_codes=["HYBRID"],
            institution_type_code="EARLY_YEARS",
        )
        self.school.refresh_from_db()
        self.assertIn(25, self.school.settings.get("learning_delivery_wedges") or [])
        self.assertEqual(
            self.school.settings.get("institution_type_pack"), "W35_EARLY_YEARS"
        )

    def test_ministry_stubs_stored(self):
        apply_learning_institution_packs(
            self.school, institution_type_code="W43_HIGHER_EDUCATION"
        )
        self.school.refresh_from_db()
        slugs = self.school.settings.get("ministry_report_stub_slugs") or []
        self.assertTrue(any("transcript" in x for x in slugs))

    def test_workflow_hints_appended(self):
        apply_learning_institution_packs(
            self.school, delivery_mode_codes=["W23_IN_PERSON"]
        )
        self.school.refresh_from_db()
        hints = self.school.settings.get("workflow_pack_hints") or []
        self.assertTrue(any("core_scheduling" in str(h) for h in hints))
