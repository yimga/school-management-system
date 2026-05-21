"""Operator direction model — launch lanes and step export."""

from django.test import SimpleTestCase

from apps.platform_runtime.tenant_onboarding_operator_direction import (
    LAUNCH_LANES,
    ONBOARDING_DIRECTION_STEPS,
    OPERATOR_ROLES,
    direction_steps_export,
)


class TenantOnboardingOperatorDirectionTests(SimpleTestCase):
    def test_launch_lanes_cover_launch_path(self):
        keys = {lane["key"] for lane in LAUNCH_LANES}
        self.assertIn("start_setup", keys)
        self.assertIn("launch", keys)

    def test_direction_steps_have_owners_and_ai_guidance(self):
        rows = direction_steps_export()
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertIn(row["owner"], OPERATOR_ROLES)
            self.assertTrue(row.get("ai_guidance"))

    def test_onboarding_direction_keys_align_with_runtime_checker(self):
        runtime_keys = {
            "academic_year",
            "students",
            "teachers",
            "guided_configuration",
            "plan_entitlements",
        }
        exported = {r["step_key"] for r in ONBOARDING_DIRECTION_STEPS}
        self.assertTrue(runtime_keys.issubset(exported))
