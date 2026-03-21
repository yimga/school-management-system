"""BR-12: command center metrics module (extracted from super_views)."""

from django.test import TestCase

from apps.schools.super_views_command_center_data import build_command_center_data


class BuildCommandCenterDataTests(TestCase):
    def test_returns_dict_with_core_keys(self):
        data = build_command_center_data()
        self.assertIsInstance(data, dict)
        self.assertIn("provisioning_sla_target_hours", data)
        self.assertIn("provisioning_sla_avg_hours", data)
        self.assertIn("support_open_count", data)
        self.assertIn("tenant_churn_risk_count", data)
        self.assertIn("recovery_rate_pct", data)
        self.assertIn("student_passport_count", data)
