"""Wedges 23–30 / 31–43: runtime apply + catalog integrity."""

from django.test import TestCase

from apps.platform_runtime.learning_institution_catalog import (
    INSTITUTION_TYPE_PACKS,
    LEARNING_DELIVERY_MODES,
    MINISTRY_REPORT_STUBS,
    normalize_delivery_code,
    normalize_institution_code,
)
from apps.platform_runtime.learning_institution_runtime import (
    apply_learning_institution_packs,
)
from apps.schools.models import School


class LearningInstitutionRuntimeTests(TestCase):
    def test_normalize_aliases(self):
        self.assertEqual(normalize_delivery_code("FACE_TO_FACE"), "W23_IN_PERSON")
        self.assertEqual(
            normalize_institution_code("HIGHER_ED"), "W43_HIGHER_EDUCATION"
        )

    def test_apply_sets_wedges_features_stubs_hints(self):
        school = School.objects.create(
            name="RT School",
            slug="rt-school",
            subdomain="rt-school",
            is_active=True,
        )
        apply_learning_institution_packs(
            school,
            delivery_mode_codes=["W25_HYBRID"],
            institution_type_code="W32_TVET",
        )
        school.refresh_from_db()
        st = school.settings or {}
        self.assertIn("W25_HYBRID", st.get("learning_delivery_modes") or [])
        self.assertEqual(st.get("institution_type_pack"), "W32_TVET")
        self.assertEqual(st.get("institution_type_wedge"), 32)
        self.assertIn(25, st.get("learning_delivery_wedges") or [])
        self.assertTrue(st.get("ministry_report_stub_slugs"))
        self.assertTrue(st.get("workflow_pack_hints"))
        self.assertTrue(st.get("report_template_hints"))
        feats = school.features or {}
        self.assertTrue(
            feats.get("tvet") or feats.get("workplace_learning"),
            msg="W32_TVET should enable tvet-related features",
        )

    def test_ministry_stub_for_every_institution_type(self):
        for pack in INSTITUTION_TYPE_PACKS:
            code = pack["code"]
            stubs = MINISTRY_REPORT_STUBS.get(code) or MINISTRY_REPORT_STUBS["DEFAULT"]
            self.assertTrue(stubs, msg=f"stubs for {code}")

    def test_delivery_labels_match_sot_count(self):
        self.assertEqual(len(LEARNING_DELIVERY_MODES), 8)
        self.assertEqual(len(INSTITUTION_TYPE_PACKS), 13)
        dw = [int(x["wedge"]) for x in LEARNING_DELIVERY_MODES]
        self.assertEqual(dw, list(range(23, 31)))
        iw = [int(x["wedge"]) for x in INSTITUTION_TYPE_PACKS]
        self.assertEqual(iw, list(range(31, 44)))
