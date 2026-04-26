"""1098/1072: Bulk letters backend page — operator summary, related CP links, markers."""

from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department


class BulkLettersOperatorMarkersTests(TestCase):
    databases = {"default"}

    def setUp(self) -> None:
        self.client = Client()
        User.objects.create_superuser(
            username="bl_op",
            email="bl@test.com",
            password="testpass123",
        )
        year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="Form 3A",
            code="F3A-2425",
        )

    def test_get_includes_evidence_markers_and_cp_before_admin(self) -> None:
        self.client.login(username="bl_op", password="testpass123")
        response = self.client.get(reverse("siteconfig:bulk_letters"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-surface="bulk-letters"', body)
        self.assertIn("data-rmc-operator-evidence-summary", body)
        self.assertIn("data-rmc-evidence-related-links", body)
        self.assertIn("Scheduled report delivery", body)
        self.assertIn("/siteconfig/reports/report-templates-catalog/", body)
        pri = body.find("Scheduled report delivery")
        adv = body.find("Advanced/Admin: report template rows")
        self.assertNotEqual(pri, -1)
        self.assertNotEqual(adv, -1)
        self.assertLess(pri, adv)
