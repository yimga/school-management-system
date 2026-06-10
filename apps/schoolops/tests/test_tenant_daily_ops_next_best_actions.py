"""Schoolops daily ops — next-best-action cards."""

from django.test import TestCase

from apps.platform_runtime.tenant_daily_ops import (
    next_best_actions_for_role,
    resolve_action_urls,
)
from apps.schools.models import School


class TenantDailyOpsNextBestActionsTests(TestCase):
    def test_admin_workflows_include_schoolops_surface(self):
        school = School.objects.create(
            name="Ops School",
            slug="ops-school",
            subdomain="ops-school",
            is_active=True,
        )
        user = type("U", (), {"role": "ADMIN"})()
        actions = resolve_action_urls(next_best_actions_for_role(school, user))
        keys = {a["key"] for a in actions}
        self.assertIn("attendance", keys)
        self.assertTrue(all("url" in a for a in actions))
