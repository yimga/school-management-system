from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.schools.models import School


class PackImpactAnalysisTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Pack Impact School",
            slug="pack-impact-school",
            subdomain="pack-impact-school",
            is_active=True,
        )

    def test_high_risk_changes_are_flagged(self):
        result = analyze_pack_impact("network-operator", pack_type="dashboard_pack", school=self.school)

        self.assertIn("high", result["impact_categories"])
        self.assertTrue(result["requires_simulation"])

    def test_impact_includes_affected_surfaces(self):
        result = analyze_pack_impact("attendance-recovery", pack_type="workflow_pack", school=self.school)

        self.assertTrue(result["affected_roles"])
        self.assertTrue(result["affected_routes"])
        self.assertTrue(result["audit_coverage"])

    def test_external_dependencies_do_not_appear_completed(self):
        # finance-approval's PSP requirement is CONDITIONAL ("...when live
        # collection is used"), so it is a go-live capability gate, not an
        # apply-time dependency. It must stay visible and uncompleted...
        result = analyze_pack_impact("finance-approval", pack_type="policy_bundle", school=self.school)

        self.assertIn("go_live_required", result["impact_categories"])
        self.assertTrue(result["go_live_required"])
        self.assertTrue(result["external_requirements_remaining"])
        self.assertFalse(result["billing_effects"]["live_psp_enabled"])

    def test_conditional_go_live_gate_does_not_escalate_risk(self):
        # ...but it must NOT be reported as a hard external dependency, which is
        # what escalates risk to "high" and forces a governance detour. A school
        # that never collects online was being blocked by a proof it will never
        # need. (This pack still requires approval — every policy_bundle does —
        # so the gate is asserted at the category level, where the difference is.)
        result = analyze_pack_impact("finance-approval", pack_type="policy_bundle", school=self.school)

        self.assertNotIn("external_required", result["impact_categories"])
        self.assertEqual(result["external_dependencies"], [])
