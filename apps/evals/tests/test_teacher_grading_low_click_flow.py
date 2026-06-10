"""Teacher grading low-click flow."""

from django.test import TestCase

from apps.platform_runtime.tenant_daily_ops import next_best_actions_for_role
from apps.schools.models import School


class TeacherGradingLowClickTests(TestCase):
    def test_teacher_gradebook_action(self):
        school = School.objects.create(
            name="Grade School",
            slug="grade-school",
            subdomain="grade-school",
            is_active=True,
        )
        user = type("U", (), {"role": "TEACHER"})()
        actions = next_best_actions_for_role(school, user)
        gradebook = [a for a in actions if a["key"] == "gradebook"]
        self.assertTrue(gradebook)
        self.assertGreaterEqual(gradebook[0]["clicks_saved"], 1)
