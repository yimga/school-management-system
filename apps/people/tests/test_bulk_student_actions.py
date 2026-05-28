"""Bulk student status service tests."""

import uuid

from django.test import TestCase

from apps.people.bulk_student_actions import bulk_set_student_status
from apps.people.models import StudentProfile
from apps.schools.models import School


def _make_school(slug_prefix: str) -> School:
    suffix = uuid.uuid4().hex[:8]
    return School.objects.create(
        slug=f"{slug_prefix}-{suffix}",
        subdomain=f"{slug_prefix}-{suffix}",
        name=f"{slug_prefix.title()} School {suffix}",
    )


class BulkStudentActionsTests(TestCase):
    def setUp(self):
        self.school = _make_school("bulk-a")
        self.student = StudentProfile.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            status=StudentProfile.Status.NEW,
            is_active=True,
            school=self.school,
        )

    def test_set_status_updates_row(self):
        outcome = bulk_set_student_status(
            student_ids=[self.student.pk],
            status=StudentProfile.Status.RETURNING,
            school=self.school,
        )
        self.assertTrue(outcome["ok"])
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, StudentProfile.Status.RETURNING)

    def test_invalid_status_rejected(self):
        with self.assertRaisesMessage(ValueError, "Unsupported status"):
            bulk_set_student_status(
                student_ids=[self.student.pk],
                status="INVALID",
                school=self.school,
            )

    def test_school_required(self):
        with self.assertRaisesMessage(ValueError, "Tenant context required"):
            bulk_set_student_status(
                student_ids=[self.student.pk],
                status=StudentProfile.Status.RETURNING,
                school=None,
            )

    def test_other_tenant_student_ids_silently_ignored(self):
        other_school = _make_school("bulk-b")
        other_student = StudentProfile.objects.create(
            first_name="Grace",
            last_name="Hopper",
            status=StudentProfile.Status.NEW,
            is_active=True,
            school=other_school,
        )
        outcome = bulk_set_student_status(
            student_ids=[self.student.pk, other_student.pk],
            status=StudentProfile.Status.RETURNING,
            school=self.school,
        )
        self.assertTrue(outcome["ok"])
        self.student.refresh_from_db()
        other_student.refresh_from_db()
        self.assertEqual(self.student.status, StudentProfile.Status.RETURNING)
        # Cross-tenant student row must NOT be mutated.
        self.assertEqual(other_student.status, StudentProfile.Status.NEW)
