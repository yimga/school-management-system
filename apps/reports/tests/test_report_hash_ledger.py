from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Term
from apps.people.models import StudentProfile
from apps.reports.models import ReportCard, ReportDocumentHash
from apps.reports.views import _record_report_hash
from apps.schools.models import School


class ReportHashLedgerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Hash School",
            slug="hash-school",
            subdomain="hash-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="hash-admin",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="First",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            position=1,
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI-HASH")
        self.specialty = Specialty.objects.create(department=self.department, name="Biology", code="BIO-HASH")
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name="Form 5",
            code="F5-HASH",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Hash",
            last_name="Student",
            student_code="HASH-001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )
        self.report_card = ReportCard.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            student=self.student,
            type=ReportCard.Type.TERM,
        )

    def test_record_report_hash_creates_ledger_entry(self):
        _record_report_hash(self.user, self.report_card, b"%PDF-sample-content")
        row = ReportDocumentHash.objects.get(report_card=self.report_card)
        self.assertEqual(len(row.sha256_hash), 64)
        self.assertEqual(row.file_size_bytes, len(b"%PDF-sample-content"))

    def test_verify_report_hash_endpoint_by_hash(self):
        _record_report_hash(self.user, self.report_card, b"pdf-one")
        row = ReportDocumentHash.objects.get(report_card=self.report_card)
        response = self.client.get(reverse("reports:verify_report_hash"), {"hash": row.sha256_hash})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("verified"))
        self.assertEqual(payload.get("report_card_id"), self.report_card.pk)

    def test_verify_report_hash_endpoint_by_report_card_id(self):
        _record_report_hash(self.user, self.report_card, b"pdf-two")
        response = self.client.get(reverse("reports:verify_report_hash"), {"report_card_id": self.report_card.pk})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("verified"))
        self.assertEqual(payload.get("student_id"), self.student.pk)

    def test_verify_report_hash_rate_limited_returns_429(self):
        with patch("apps.reports.views.throttle_ip_request", return_value=(False, 60)):
            response = self.client.get(reverse("reports:verify_report_hash"), {"report_card_id": self.report_card.pk})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")
