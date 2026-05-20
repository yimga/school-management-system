from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.people.models import TeacherProfile
from apps.people.schema_repair import ensure_teacherprofile_updated_at_column
from apps.people.user_profile_access import safe_teacher_profile

User = get_user_model()


class TeacherProfileUpdatedAtHealTests(TestCase):
    def test_ensure_column_idempotent(self):
        self.assertFalse(ensure_teacherprofile_updated_at_column())
        self.assertFalse(ensure_teacherprofile_updated_at_column())

    def test_safe_teacher_profile_without_row(self):
        user = User.objects.create_user(
            username="heal_no_tp",
            password="x",
            role=getattr(User.Role, "TEACHER", "TEACHER"),
        )
        self.assertIsNone(safe_teacher_profile(user))

    def test_safe_teacher_profile_with_row(self):
        user = User.objects.create_user(
            username="heal_with_tp",
            password="x",
            role=getattr(User.Role, "TEACHER", "TEACHER"),
        )
        TeacherProfile.objects.create(user=user, staff_id="T-HEAL-1")
        profile = safe_teacher_profile(user)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.staff_id, "T-HEAL-1")

    def test_updated_at_column_present_after_migrate(self):
        with connection.cursor() as cursor:
            columns = {
                col.name
                for col in connection.introspection.get_table_description(
                    cursor, "people_teacherprofile"
                )
            }
        self.assertIn("updated_at", columns)
