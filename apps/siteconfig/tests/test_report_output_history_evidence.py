"""1072: Read-only report output history evidence from real ReportCard rows."""

from __future__ import annotations

from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Term
from apps.people.models import StudentProfile
from apps.reports.models import ReportCard, ReportCardAudit, ReportDocumentHash
from apps.siteconfig.models import Plan
from apps.schools.models import School

_T_HOST = "rout.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class ReportOutputHistoryEvidenceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls) -> None:
        cls.plan = Plan.objects.create(
            name="ReportOutputPlan",
            slug="report-output-plan",
            included_features=["reports"],
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Report Output School",
            slug="rout",
            subdomain="rout",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.user = User.objects.create_user(
            username="report_output_adm",
            password="p" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        cls.user.feature_permissions.add(cls.perm_settings)
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        cls.term = Term.objects.create(
            academic_year=cls.year,
            name="First",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            position=1,
            is_active=True,
        )
        cls.department = Department.objects.create(
            school=cls.school,
            name="Science",
            code="SCI-ROUT",
        )
        cls.specialty = Specialty.objects.create(
            department=cls.department,
            name="Biology",
            code="BIO-ROUT",
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=cls.department,
            name="Form 5",
            code="F5-ROUT",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Report",
            last_name="Student",
            student_code="ROUT-001",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=cls.specialty,
            is_active=True,
        )
        cls.report_card = ReportCard.objects.create(
            school=cls.school,
            academic_year=cls.year,
            term=cls.term,
            student=cls.student,
            type=ReportCard.Type.TERM,
            pdf_file="tenants/rout/reports/sample.pdf",
        )
        ReportDocumentHash.objects.create(
            school=cls.school,
            report_card=cls.report_card,
            sha256_hash="a" * 64,
            file_size_bytes=128,
            generated_by=cls.user,
        )
        ReportCardAudit.objects.create(
            report_card=cls.report_card,
            user=cls.user,
            action="GENERATED",
            metadata={"source": "test"},
        )

    def test_settings_manager_sees_real_output_history_markers(self) -> None:
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="report_output_adm", password="p" * 8)
        path = reverse(
            "siteconfig:report_output_history_evidence", urlconf="config.tenant_urls"
        )
        self.assertIn("/siteconfig/reports/output-history-evidence/", path)
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-surface="report-output-history-evidence"', body)
        self.assertIn('data-cp-evidence-surface="report-output-history"', body)
        self.assertIn("data-rmc-operator-evidence-summary", body)
        self.assertIn("data-rmc-evidence-related-links", body)
        self.assertIn("data-rmc-report-bulk-evidence", body)
        self.assertIn("Report Student", body)
        self.assertIn("Hash ledger", body)
        self.assertIn("Audit events", body)

    def test_related_links_precede_advanced_admin_fallback(self) -> None:
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="report_output_adm", password="p" * 8)
        path = reverse(
            "siteconfig:report_output_history_evidence", urlconf="config.tenant_urls"
        )
        body = c.get(path).content.decode("utf-8", errors="replace")
        primary = body.find("Scheduled report delivery")
        advanced = body.find("Advanced/Admin: report card rows")
        self.assertNotEqual(primary, -1)
        self.assertNotEqual(advanced, -1)
        self.assertLess(primary, advanced)

