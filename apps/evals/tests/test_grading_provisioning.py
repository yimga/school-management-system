"""10X studio seeding — per-school GradingScale auto-provisioned from the country.

Before this, the country pack computed a grading scale into school.settings but no
GradingScale model row was created at provision, so a new school showed "no grading scale
configured" until an admin manually ran the wizard. ensure_local_grading_scale closes the
gap: country preset → scale type → per-school default GradingScale + matching default
AssessmentWeights, idempotent, never overriding an admin/wizard choice.
"""

from django.test import SimpleTestCase, TestCase


class ScaleConfigTests(SimpleTestCase):
    def test_preset_map_values_are_valid_scale_types(self):
        from apps.evals.grading_provisioning import (
            _PRESET_TO_SCALE_TYPE,
            _VALID_SCALE_TYPES,
        )

        for preset, scale in _PRESET_TO_SCALE_TYPE.items():
            self.assertIn(scale, _VALID_SCALE_TYPES, preset)

    def test_key_presets_map_as_expected(self):
        from apps.evals.grading_provisioning import _PRESET_TO_SCALE_TYPE

        self.assertEqual(_PRESET_TO_SCALE_TYPE["francophone_bac"], "numeric_0_20")
        self.assertEqual(_PRESET_TO_SCALE_TYPE["american"], "gpa_4_0")
        self.assertEqual(_PRESET_TO_SCALE_TYPE["british_igcse"], "letter_a_e")
        self.assertEqual(_PRESET_TO_SCALE_TYPE["west_african_waec"], "percentage")

    def test_scale_config_percentage(self):
        from apps.evals.grading_provisioning import _scale_config

        cfg = _scale_config("percentage")
        self.assertEqual(cfg["score_scale"], 100)
        self.assertEqual(cfg["pass_threshold"], 50.0)
        self.assertEqual(cfg["grade_thresholds"]["A"], 80.0)

    def test_scale_config_numeric_0_20(self):
        from apps.evals.grading_provisioning import _scale_config

        cfg = _scale_config("numeric_0_20")
        self.assertEqual(cfg["score_scale"], 20)
        self.assertEqual(cfg["pass_threshold"], 10.0)


class GradingProvisioningDBTests(TestCase):
    def _school(self, **kw):
        import uuid

        from apps.schools.models import School

        tag = uuid.uuid4().hex[:10]
        return School.objects.create(
            name="GP " + tag, slug=f"gp-{tag}", subdomain=f"gp-{tag}", **kw
        )

    def test_seeds_country_scale_and_default_weights(self):
        from apps.academics.models import AcademicYear
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import AssessmentWeights, GradingScale

        school = self._school(country_code="FR")  # francophone_bac → numeric_0_20
        ay = AcademicYear.objects.create(
            school=school, name="2025/2026", start_date="2025-09-01", end_date="2026-07-31"
        )
        res = ensure_local_grading_scale(school, academic_year=ay)
        self.assertTrue(res["ok"])
        scale = GradingScale.objects.get(school=school, is_default=True)
        self.assertEqual(scale.scale_type, "numeric_0_20")
        self.assertTrue(
            AssessmentWeights.objects.filter(
                school=school, academic_year=ay, term=None, classroom=None
            ).exists()
        )

    def test_idempotent_second_call_skips(self):
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import GradingScale

        school = self._school(country_code="US")
        ensure_local_grading_scale(school)
        res2 = ensure_local_grading_scale(school)
        self.assertEqual(res2.get("skipped"), "default_scale_exists")
        self.assertEqual(GradingScale.objects.filter(school=school, is_default=True).count(), 1)

    def test_respects_existing_admin_default(self):
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import GradingScale

        school = self._school(country_code="FR")
        GradingScale.objects.create(
            school=school, code="wizard-default", name="Admin pick",
            scale_type="percentage", is_default=True, is_active=True,
        )
        res = ensure_local_grading_scale(school)
        self.assertEqual(res.get("skipped"), "default_scale_exists")
        # Admin's percentage choice preserved, not overridden by FR→numeric_0_20.
        self.assertEqual(
            GradingScale.objects.get(school=school, is_default=True).scale_type, "percentage"
        )
