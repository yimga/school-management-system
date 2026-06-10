"""Teacher attendance low-click flow."""

from django.test import TestCase

from apps.platform_runtime.tenant_daily_ops import next_best_actions_for_role
from apps.schools.models import School


class TeacherAttendanceLowClickTests(TestCase):
    def test_teacher_attendance_action(self):
        school = School.objects.create(
            name="Att School",
            slug="att-school",
            subdomain="att-school",
            is_active=True,
        )
        user = type("U", (), {"role": "TEACHER"})()
        actions = next_best_actions_for_role(school, user)
        att = [a for a in actions if a["key"] == "attendance"]
        self.assertTrue(att)
        self.assertGreaterEqual(att[0]["clicks_saved"], 1)
