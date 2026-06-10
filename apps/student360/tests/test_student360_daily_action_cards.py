"""Student360 daily action cards."""

from django.test import TestCase

from apps.platform_runtime.tenant_daily_ops import next_best_actions_for_role
from apps.schools.models import School


class Student360DailyActionCardsTests(TestCase):
    def test_parent_student360_action(self):
        school = School.objects.create(
            name="S360 School",
            slug="s360-school",
            subdomain="s360-school",
            is_active=True,
        )
        user = type("U", (), {"role": "PARENT"})()
        actions = next_best_actions_for_role(school, user)
        self.assertTrue(any(a["key"] == "student360" for a in actions))
