"""Tests for `fulfill_pending_erasure` — closes the gap between EraseRequest
status flips and actual PII scrubbing."""

from django.test import TestCase

from apps.accounts.models import User
from apps.compliance.gdpr_services import fulfill_pending_erasure
from apps.compliance.models import EraseRequest
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class FulfillPendingErasureTests(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="TFE",
            defaults={
                "name": "Test Fulfill Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name="Fulfill School",
            slug="fulfill-school",
            subdomain="fulfill-school",
            is_active=True,
            default_region=self.region,
        )
        self.student_user = User.objects.create_user(
            username="fpe_student",
            email="fpe.student@example.com",
            password="pass",
            role=User.Role.STUDENT,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            first_name="Alex",
            last_name="Doe",
            student_code="FPE-001",
            parent_phone="555-0100",
        )
        self.operator = User.objects.create_user(
            username="fpe_operator", email="op@example.com", password="pass"
        )

    def _make_request(self, status=EraseRequest.Status.PENDING):
        return EraseRequest.objects.create(
            school=self.school,
            requested_by=self.operator,
            subject_user=self.student_user,
            status=status,
            reason="user request",
        )

    def test_fulfills_pending_request_and_scrubs(self):
        er = self._make_request()
        result = fulfill_pending_erasure(er.pk, fulfilled_by_user_id=self.operator.pk)
        self.assertTrue(result["ok"], result)
        er.refresh_from_db()
        self.assertEqual(er.status, EraseRequest.Status.COMPLETED)
        self.assertIsNotNone(er.completed_at)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Deleted")
        self.assertEqual(self.student.parent_phone, "")

    def test_dry_run_does_not_mutate_status_or_pii(self):
        er = self._make_request()
        result = fulfill_pending_erasure(er.pk, dry_run=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        er.refresh_from_db()
        self.assertEqual(er.status, EraseRequest.Status.PENDING)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Alex")

    def test_terminal_status_is_refused(self):
        er = self._make_request(status=EraseRequest.Status.COMPLETED)
        result = fulfill_pending_erasure(er.pk)
        self.assertFalse(result["ok"])
        self.assertIn("terminal state", result["error"])

    def test_rejected_request_is_refused(self):
        er = self._make_request(status=EraseRequest.Status.REJECTED)
        result = fulfill_pending_erasure(er.pk)
        self.assertFalse(result["ok"])
        self.assertIn("terminal state", result["error"])

    def test_unknown_request_returns_error(self):
        result = fulfill_pending_erasure(999999)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "EraseRequest not found")

    def test_non_student_subject_returns_unsupported(self):
        # Teacher / parent / staff users are not yet handled.
        teacher_user = User.objects.create_user(
            username="fpe_teacher",
            email="teacher@example.com",
            password="pass",
            role=User.Role.TEACHER,
        )
        er = EraseRequest.objects.create(
            school=self.school,
            requested_by=self.operator,
            subject_user=teacher_user,
            status=EraseRequest.Status.PENDING,
        )
        result = fulfill_pending_erasure(er.pk)
        self.assertFalse(result["ok"])
        self.assertIn("unsupported_subject_kind", result["error"])
        er.refresh_from_db()
        self.assertEqual(er.status, EraseRequest.Status.PENDING)

    def test_other_school_student_not_visible(self):
        # Tenant isolation: an erasure request scoped to school A must not
        # mutate a student in school B even if subject_user_id matches.
        other_school = School.objects.create(
            name="Other",
            slug="other-school",
            subdomain="other-school",
            is_active=True,
            default_region=self.region,
        )
        er = EraseRequest.objects.create(
            school=other_school,
            requested_by=self.operator,
            subject_user=self.student_user,
            status=EraseRequest.Status.PENDING,
        )
        result = fulfill_pending_erasure(er.pk)
        self.assertFalse(result["ok"])
        self.assertIn("unsupported_subject_kind", result["error"])
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Alex")
