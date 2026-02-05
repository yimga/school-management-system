"""Tests for Report Library and Bulk Letters views (RBAC and basic behaviour)."""
from datetime import date
from io import BytesIO
from unittest.mock import patch
import zipfile

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile


class ReportLibraryRBACTestCase(TestCase):
    """Report Library requires settings.manage (or superuser)."""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="super_rl",
            email="super@test.com",
            password="testpass123",
        )
        self.staff_no_perm = User.objects.create_user(
            username="staff_rl",
            email="staff@test.com",
            password="testpass123",
            is_staff=True,
        )

    def test_report_library_anonymous_redirected(self):
        response = self.client.get(reverse("siteconfig:report_library"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    def test_report_library_superuser_200(self):
        self.client.login(username="super_rl", password="testpass123")
        response = self.client.get(reverse("siteconfig:report_library"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Reports", response.content)

    def test_report_library_staff_without_permission_forbidden(self):
        self.client.login(username="staff_rl", password="testpass123")
        response = self.client.get(reverse("siteconfig:report_library"))
        self.assertIn(response.status_code, (302, 403))


class BulkLettersRBACTestCase(TestCase):
    """Bulk Letters requires settings.manage (or superuser)."""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="super_bl",
            email="super@test.com",
            password="testpass123",
        )

    def test_bulk_letters_anonymous_redirected(self):
        response = self.client.get(reverse("siteconfig:bulk_letters"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    def test_bulk_letters_get_superuser_200(self):
        self.client.login(username="super_bl", password="testpass123")
        response = self.client.get(reverse("siteconfig:bulk_letters"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Bulk Letters", response.content)
        self.assertIn(b"Letter body", response.content)


class BulkLettersPostTestCase(TestCase):
    """Bulk Letters POST: validation and zip response when Pandoc is mocked."""

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="super_bl",
            email="super@test.com",
            password="testpass123",
        )
        year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="Form 3A",
            code="F3A-2425",
        )
        StudentProfile.objects.create(
            first_name="Jane",
            last_name="Doe",
            student_code="STU001",
            classroom=self.classroom,
        )

    @patch("apps.portal.document_generation.html_to_odt")
    def test_bulk_letters_post_returns_zip(self, mock_html_to_odt):
        mock_html_to_odt.return_value = b"fake-odt-bytes"
        self.client.force_login(self.superuser)
        # GET form first so we have session/CSRF
        self.client.get(reverse("siteconfig:bulk_letters"))
        response = self.client.post(
            reverse("siteconfig:bulk_letters"),
            data={
                "classroom_id": str(self.classroom.id),
                "letter_body": "<p>Dear {{ first_name }},</p>",
            },
        )
        self.assertEqual(
            response.status_code,
            200,
            msg="Expected 200 with zip; got %s. Body: %s" % (response.status_code, response.content[:400]),
        )
        content_type = response.get("Content-Type", "")
        self.assertIn("application/zip", content_type, "Response should be a zip file")
        buf = BytesIO(response.content)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            self.assertTrue(any(n.endswith(".odt") for n in names), "Zip should contain at least one .odt")
        self.assertIn("attachment", response.get("Content-Disposition", ""))
