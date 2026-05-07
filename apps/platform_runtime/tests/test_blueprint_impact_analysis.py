from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.schools.models import School


class BlueprintImpactAnalysisTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Impact School",
            slug="impact-school",
            subdomain="impact-school",
            is_active=True,
        )

    def test_high_risk_changes_are_flagged(self):
        impact = analyze_blueprint_impact("private-secondary-school", school=self.school)

        self.assertIn("high", impact["impact_categories"])
        self.assertTrue(impact["requires_confirmation"])

    def test_external_dependencies_do_not_appear_completed(self):
        impact = analyze_blueprint_impact("international-school", school=self.school)

        self.assertIn("external_required", impact["impact_categories"])
        self.assertIn(
            "multi_currency_live_collection",
            impact["summary"]["external_dependencies_remaining"],
        )

    def test_destructive_changes_require_confirmation_contract(self):
        impact = analyze_blueprint_impact("private-primary-school", school=self.school)

        self.assertTrue(impact["requires_confirmation"])
        self.assertNotIn("destructive", impact["impact_categories"])

    def test_impact_result_includes_affected_surface_groups(self):
        impact = analyze_blueprint_impact("boarding-school", school=self.school)

        self.assertIn("Boarding manager", impact["summary"]["roles_gain_access"])
        self.assertIn("Leave request", impact["summary"]["workflows_activate"])
        self.assertIn("Boarding operations", impact["summary"]["dashboards_change"])
        self.assertIn("Incident audit", impact["summary"]["policies_active"])

    def test_tenant_cannot_analyze_operator_required_blueprint_as_applyable(self):
        impact = analyze_blueprint_impact(
            "multi-campus-network",
            school=self.school,
            platform_operator=False,
        )

        self.assertFalse(impact["can_apply"])
        self.assertIn("tenant_blocked", impact["impact_categories"])
        self.assertIn("platform_only", impact["impact_categories"])
