"""PolicyBundle grading JSON-Logic templates (global academic kernel)."""

from django.test import SimpleTestCase, TestCase

from apps.policies.grading_nuance_templates import (
    attach_grading_nuance_to_policy,
    grading_nuance_templates_for_preset,
    sync_grading_nuance_from_policy,
)
from apps.policies.resolver import get_effective_policy
from apps.schools.models import School
from apps.siteconfig.models import CustomNuance
from apps.siteconfig.nuance_engine import apply_nuance


class GradingNuanceTemplateUnitTests(SimpleTestCase):
    def test_waec_preset_has_report_card_template(self):
        tpl = grading_nuance_templates_for_preset("west_african_waec")
        self.assertIn("report_card_avg", tpl)
        self.assertIsInstance(tpl["report_card_avg"].get("logic_data"), dict)

    def test_attach_verifies_templates(self):
        policy: dict = {}
        attach_grading_nuance_to_policy(policy, "francophone_bac")
        templates = policy.get("grading", {}).get("nuance_templates") or {}
        self.assertIn("report_card_avg", templates)


class GradingNuancePolicyIntegrationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Nuance Policy School",
            slug="nuance-policy-school",
            subdomain="nuance-policy-school",
            country_code="CM",
            is_active=True,
        )

    def test_resolver_merges_nuance_templates(self):
        policy = get_effective_policy(self.school)
        templates = (policy.get("grading") or {}).get("nuance_templates") or {}
        self.assertIn("report_card_avg", templates)

    def test_sync_and_apply_weighted_average(self):
        sync_grading_nuance_from_policy(self.school)
        self.assertTrue(
            CustomNuance.objects.filter(
                school=self.school, hook_point="report_card_avg", is_active=True
            ).exists()
        )
        result = apply_nuance(
            self.school,
            "report_card_avg",
            {
                "weighted_sum": 30.0,
                "coefficient_total": 5.0,
                "scale_max": 20.0,
                "scores_by_subject": {},
                "coefficients": {},
            },
        )
        self.assertEqual(result, 6.0)
