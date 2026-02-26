from django.test import TestCase

from apps.people.models import StudentProfile
from apps.schools.models import School


class StudentSoftDeleteTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Soft Delete School",
            slug="soft-delete-school",
            subdomain="soft-delete-school",
            is_active=True,
        )

    def test_student_delete_sets_deleted_at_and_keeps_row(self):
        student = StudentProfile.objects.create(
            school=self.school,
            first_name="Soft",
            last_name="Student",
            is_active=True,
        )
        student_id = student.pk

        deleted_count, _ = student.delete()

        self.assertEqual(deleted_count, 1)
        self.assertTrue(StudentProfile.objects.filter(pk=student_id).exists())
        student.refresh_from_db()
        self.assertIsNotNone(student.deleted_at)
        self.assertFalse(student.is_active)

    def test_student_hard_delete_removes_row(self):
        student = StudentProfile.objects.create(
            school=self.school,
            first_name="Hard",
            last_name="Delete",
            is_active=True,
        )
        student_id = student.pk

        student.delete(hard_delete=True)

        self.assertFalse(StudentProfile.objects.filter(pk=student_id).exists())
