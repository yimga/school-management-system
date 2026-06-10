"""Permission-to-pay / parent fees low-click flow."""

from django.test import TestCase

from apps.platform_runtime.tenant_daily_ops import next_best_actions_for_role
from apps.schools.models import School


class PermissionToPayLowClickTests(TestCase):
    def test_parent_fees_action(self):
        school = School.objects.create(
            name="Pay School",
            slug="pay-school",
            subdomain="pay-school",
            is_active=True,
        )
        user = type("U", (), {"role": "PARENT"})()
        actions = next_best_actions_for_role(school, user)
        fees = [a for a in actions if a["key"] == "fees"]
        self.assertTrue(fees)
        self.assertGreaterEqual(fees[0]["clicks_saved"], 1)
