from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_simulation import simulate_pack
from apps.schools.models import School


class PackSimulationEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Pack Simulation School",
            slug="pack-simulation-school",
            subdomain="pack-simulation-school",
            is_active=True,
        )

    def test_workflow_simulation_is_non_mutating(self):
        before = PackInstallation.objects.count()

        result = simulate_pack("attendance-recovery", pack_type="workflow_pack", school=self.school)

        self.assertEqual(result["result"], "simulated")
        self.assertIn("notify_guardian", result["actions_that_would_run"])
        self.assertEqual(PackInstallation.objects.count(), before)

    def test_dashboard_simulation_returns_layout_widgets_actions(self):
        result = simulate_pack("school-command-center", pack_type="dashboard_pack", school=self.school)

        self.assertTrue(result["layout"])
        self.assertTrue(result["widgets"])
        self.assertTrue(result["actions_that_would_run"])

    def test_policy_simulation_returns_approval_result(self):
        result = simulate_pack("finance-approval", pack_type="policy_bundle", school=self.school)

        self.assertEqual(result["decision"], "requires_approval")
        self.assertTrue(result["audit_requirements"])

    def test_unsafe_simulation_cannot_cross_tenant_without_school(self):
        result = simulate_pack("attendance-recovery", pack_type="workflow_pack", school=None)

        self.assertEqual(result["result"], "blocked")
        self.assertIn("tenant_required", result["blocked_reasons"])
