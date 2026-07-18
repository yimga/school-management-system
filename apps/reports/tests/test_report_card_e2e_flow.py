"""End-to-end: staff publishes term results → parent downloads term report PDF."""

import json
from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import Evaluation, GradeApprovalRequest
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.registries.models import CountryRegistry
from apps.reports.models import ReportCard, ReportDocumentHash, TermPublishStatus
from apps.reports.views import verify_report_hash
from apps.schools.models import School, SchoolMembership


_MOCK_PDF = b"%PDF-1.4 report-card-e2e-mock"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReportCardPublishParentE2ETests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Report E2E School",
            slug="report-e2e-school",
            subdomain="report-e2e-school",
            country_code="CM",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="staff_report_e2e",
            password="testpass123",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.staff,
            school=self.school,
            is_primary=True,
        )
        self.parent = User.objects.create_user(
            username="parent_report_e2e",
            password="testpass123",
            role=User.Role.PARENT,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="First",
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 15),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(
            school=self.school, name="Science", code="SCI"
        )
        specialty = Specialty.objects.create(
            school=self.school, department=department, name="Physics", code="PHY"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=department,
            name="SS1A",
            code="SS1A",
        )
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.subject_assignment = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=specialty,
            subject=subject,
            coefficient=1,
        )
        teacher_user = User.objects.create_user(
            username="teacher_report_e2e",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        teacher = TeacherProfile.objects.create(
            school=self.school, user=teacher_user
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Jane",
            last_name="Doe",
            student_code="STU-E2E-1",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            is_active=True,
        )
        StudentGuardian.objects.create(
            student=self.student,
            guardian_user=self.parent,
            can_view_results=True,
            relationship=StudentGuardian.Relationship.GUARDIAN,
        )
        Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student,
            teacher=teacher,
            seq1_score=14,
            seq2_score=15,
            exam_score=16,
            remarks="Solid term",
        )
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={
                "enable_parent_portal": True,
                "enable_reports_pdf": True,
                "report_downloads_enabled": True,
                "grade_approval_enabled": True,
                "reports_require_approved_grades_before_publish": True,
                "reports_use_approved_grades_only": True,
                "backend_feature_flags": {
                    "block_report_download_if_outstanding_balance": False,
                },
            },
        )
        GradeApprovalRequest.objects.create(
            teacher=teacher,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            entries=[
                {
                    "student_id": self.student.id,
                    "scores": {"seq1": "14", "seq2": "15", "exam": "16"},
                }
            ],
            summary={"total_students": 1, "submitted_rows": 1},
            status=GradeApprovalRequest.Status.APPROVED,
            requested_by=teacher_user,
        )

    @mock.patch("apps.reports.views.render_pdf_bytes", return_value=_MOCK_PDF)
    def test_staff_publish_then_parent_downloads_pdf(self, _mock_pdf):
        self.client.force_login(self.staff)
        publish_resp = self.client.post(
            reverse("reports:publish_term_results"),
            data={
                "year": self.year.id,
                "term": self.term.id,
                "publish_school": "1",
            },
        )
        self.assertEqual(publish_resp.status_code, 302)
        self.assertTrue(
            TermPublishStatus.objects.filter(
                academic_year=self.year,
                term=self.term,
                classroom__isnull=True,
                is_published=True,
            ).exists()
        )

        self.client.force_login(self.parent)
        download_url = reverse(
            "reports:parent_download_term_report",
            kwargs={"student_id": self.student.id},
        )
        download_resp = self.client.get(download_url)
        self.assertEqual(download_resp.status_code, 200)
        self.assertEqual(download_resp["Content-Type"], "application/pdf")
        self.assertTrue(download_resp.content.startswith(b"%PDF"))
        self.assertTrue(
            ReportCard.objects.filter(
                student=self.student,
                academic_year=self.year,
                term=self.term,
            ).exists()
        )
        report_card = ReportCard.objects.get(
            student=self.student,
            academic_year=self.year,
            term=self.term,
        )
        hash_row = ReportDocumentHash.objects.get(report_card=report_card)
        self.assertEqual(len(hash_row.sha256_hash), 64)
        verify_resp = self.client.get(
            reverse("reports:verify_report_hash"),
            {"hash": hash_row.sha256_hash},
        )
        self.assertEqual(verify_resp.status_code, 200)
        self.assertTrue(verify_resp.json().get("verified"))

    @mock.patch("apps.reports.views.render_pdf_bytes", return_value=_MOCK_PDF)
    def test_staff_publish_then_parent_html_shows_scale_aware_grade(self, _mock_pdf):
        from apps.reports.services import term_report_context

        self.client.force_login(self.staff)
        publish_resp = self.client.post(
            reverse("reports:publish_term_results"),
            data={
                "year": self.year.id,
                "term": self.term.id,
                "publish_school": "1",
            },
        )
        self.assertEqual(publish_resp.status_code, 302)

        expected_grade = term_report_context(
            self.student, self.year, self.term
        )["rows"][0]["grade_label"]
        self.assertTrue(expected_grade, "term row should expose a scale-aware grade label")

        self.client.force_login(self.parent)
        html_url = reverse(
            "portal:parent_child_results",
            kwargs={"student_id": self.student.id},
        )
        html_resp = self.client.get(html_url)
        self.assertEqual(html_resp.status_code, 200)
        body = html_resp.content.decode()
        self.assertIn("Grade", body)
        self.assertIn(expected_grade, body)
        self.assertIn("Mathematics", body)

    # Drive the REAL view function directly (RequestFactory), mocking only the
    # ORTHOGONAL gates (portal toggle, publish/clearance checks, PDF render) so the
    # test deterministically reaches the production ``get_or_create`` create path.
    # The full Client E2E false-reds locally because the config cascade reports
    # ``enable_parent_portal``/reports flags as off (host-split harness), which is
    # unrelated to the school-stamping bug under test.
    @mock.patch(
        "apps.accounts.decorators.get_effective_site_settings",
        return_value=SimpleNamespace(),
    )
    @mock.patch("apps.reports.views.render_pdf_bytes", return_value=_MOCK_PDF)
    @mock.patch("apps.reports.views._reports_enabled", return_value=True)
    @mock.patch("apps.reports.views.is_term_published", return_value=True)
    @mock.patch("apps.reports.views.student_has_financial_clearance", return_value=True)
    @mock.patch("apps.reports.views.student_has_outstanding_returns", return_value=False)
    def test_report_card_stamps_school_so_tenant_scoped_verify_resolves(self, *_mocks):
        """The REAL create path must stamp ReportCard.school, so QR/hash verification
        on the tenant host (where request.school is set) resolves instead of 404ing.

        Fails against HEAD: the create path omitted ``school=``, the row landed
        NULL-school, ``_record_report_hash`` stamped the ledger row NULL-school too,
        and ``verify_report_hash`` filters ``report_card__school=school`` → no match →
        404 for every tenant. The other E2E tests miss this because the Django test
        client leaves ``request.school`` unset, so the tenant-scoping branch never runs.
        """
        from apps.reports.views import parent_download_term_report

        factory = RequestFactory()

        # Parent downloads the term report -> production create path runs.
        dl_req = factory.get(
            reverse(
                "reports:parent_download_term_report",
                kwargs={"student_id": self.student.id},
            )
        )
        dl_req.user = self.parent
        dl_resp = parent_download_term_report(dl_req, student_id=self.student.id)
        self.assertEqual(dl_resp.status_code, 200)

        report_card = ReportCard.objects.get(
            student=self.student, academic_year=self.year, term=self.term
        )
        # Direct assertion on the fix: the row must carry the owning school.
        self.assertEqual(report_card.school_id, self.school.id)

        hash_row = ReportDocumentHash.objects.get(report_card=report_card)
        # The denormalized ledger school must be stamped too (unscoped PII otherwise).
        self.assertEqual(hash_row.school_id, self.school.id)

        # Reproduce the tenant host: request.school is resolved by TenantMiddleware.
        # Call the verifier directly with a tenant-scoped request (avoids host-split
        # urlconf traps). On HEAD this returns 404; after the fix it resolves.
        v_req = factory.get(
            reverse("reports:verify_report_hash"),
            {"hash": hash_row.sha256_hash},
        )
        v_req.school = self.school
        v_resp = verify_report_hash(v_req)
        self.assertEqual(v_resp.status_code, 200)
        self.assertTrue(json.loads(v_resp.content).get("verified"))
