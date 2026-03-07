"""
RBAC: Teacher pay history shows only the current teacher's data (Phase 10.2).
"""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.people.models import TeacherProfile, TeacherPayRecord


class TeacherPayHistoryRBACTest(TestCase):
    """Ensure teacher cannot see another teacher's payroll data."""

    def setUp(self):
        self.teacher_a_user = User.objects.create_user(
            username="teachera",
            password="testpass",
            role=User.Role.TEACHER,
        )
        self.teacher_b_user = User.objects.create_user(
            username="teacherb",
            password="testpass",
            role=User.Role.TEACHER,
        )
        self.profile_a = TeacherProfile.objects.create(user=self.teacher_a_user)
        self.profile_b = TeacherProfile.objects.create(user=self.teacher_b_user)
        TeacherPayRecord.objects.create(
            teacher=self.profile_a,
            record_type=TeacherPayRecord.RecordType.PAY,
            amount=1000,
            effective_date=date(2025, 1, 15),
        )
        TeacherPayRecord.objects.create(
            teacher=self.profile_b,
            record_type=TeacherPayRecord.RecordType.PAY,
            amount=2000,
            effective_date=date(2025, 1, 15),
        )

    def test_teacher_pay_history_shows_only_own_records(self):
        """Logged-in teacher sees only their own pay records."""
        self.client.force_login(self.teacher_a_user)
        response = self.client.get(reverse("portal:teacher_pay_history"))
        self.assertEqual(response.status_code, 200)
        pay_records = list(response.context.get("pay_records", []))
        self.assertGreater(len(pay_records), 0)
        for record in pay_records:
            self.assertEqual(record.teacher_id, self.profile_a.id, "Pay records must belong to logged-in teacher")

    def test_teacher_b_sees_only_own_records(self):
        """Teacher B sees only their pay, not Teacher A's."""
        self.client.force_login(self.teacher_b_user)
        response = self.client.get(reverse("portal:teacher_pay_history"))
        self.assertEqual(response.status_code, 200)
        pay_records = list(response.context.get("pay_records", []))
        self.assertGreater(len(pay_records), 0)
        for record in pay_records:
            self.assertEqual(record.teacher_id, self.profile_b.id)
