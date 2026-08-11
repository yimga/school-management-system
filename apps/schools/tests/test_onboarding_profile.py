from django.test import SimpleTestCase

from apps.schools.onboarding_profile import normalize_institution_profile


class InstitutionProfileNormalizationTests(SimpleTestCase):
    def test_strict_boundary_reports_invalid_choices_numbers_and_lists(self):
        result = normalize_institution_profile(
            {
                "organization_scope": "planetary",
                "student_capacity": "1.5",
                "campus_count": "10001",
                "operational_services": ["boarding", "teleportation"],
            },
            strict=True,
        )
        self.assertEqual(
            {issue.code for issue in result.errors},
            {"unsupported_choice", "invalid_integer", "out_of_range", "unsupported_list_choice"},
        )
        self.assertEqual(result.values["organization_scope"], "single")
        self.assertEqual(result.values["student_capacity"], 0)
        self.assertEqual(result.values["campus_count"], 10000)
        self.assertEqual(result.values["operational_services"], ["boarding"])

    def test_forgiving_legacy_boundary_repairs_values_as_warnings(self):
        result = normalize_institution_profile(
            {"connectivity_profile": "dial-up", "staff_count": object()}
        )
        self.assertFalse(result.errors)
        self.assertEqual(len(result.warnings), 2)
        self.assertEqual(result.values["connectivity_profile"], "mixed")
        self.assertEqual(result.values["staff_count"], 0)

    def test_multi_campus_and_scale_inference_are_deterministic(self):
        result = normalize_institution_profile(
            {
                "organization_scope": "network",
                "learner_scale": "1000-4999",
                "operating_model": "mixed",
                "operational_services": ["transport", "transport"],
            },
            strict=True,
        )
        self.assertEqual(result.values["campus_count"], 2)
        self.assertEqual(result.values["student_capacity"], 1500)
        self.assertEqual(result.values["operational_services"], ["boarding", "transport"])
        self.assertEqual(
            {issue.code for issue in result.warnings},
            {"inferred_multi_campus_count", "inferred_capacity_from_band"},
        )

    def test_empty_profile_has_safe_non_entitling_defaults(self):
        result = normalize_institution_profile(None, strict=True)
        self.assertFalse(result.issues)
        self.assertEqual(result.values["organization_scope"], "single")
        self.assertEqual(result.values["automation_preference"], "balanced")
        self.assertEqual(result.values["migration_complexity"], "none")
        self.assertEqual(result.values["session_pattern"], "single")
        self.assertEqual(result.values["governance_profile"], "standard")

    def test_extensible_curriculum_code_rejects_markup_and_accepts_registry_slug(self):
        invalid = normalize_institution_profile(
            {"curriculum_board": "<script>alert(1)</script>"}, strict=True
        )
        valid = normalize_institution_profile(
            {"curriculum_board": "gce-bac"}, strict=True
        )
        self.assertEqual([issue.code for issue in invalid.errors], ["invalid_slug_code"])
        self.assertEqual(invalid.values["curriculum_board"], "")
        self.assertFalse(valid.errors)
        self.assertEqual(valid.values["curriculum_board"], "gce-bac")
