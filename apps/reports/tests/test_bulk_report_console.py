"""Bulk report cards: group by class OR specialty, print merged, share offline-first.

Single-card generation existed; a school still could not print a whole class in
one go, could not organise a technical college's cards by specialty, and had no
offline share path. These lock the new contract:

* the group axis follows ``school_type`` (base → class, technical/STEM →
  specialty) and an explicit ``report_card_group_mode`` config override wins;
* ``generate_term_report_cards`` can now scope to a specialty, not just a class —
  before this the ``specialty`` argument did not exist (the test could not have
  been written), which is the failing-first proof;
* ``build_group_report_pdf`` merges a group into ONE print-ready PDF and the ZIP
  path bundles one file per student;
* the offline ``report_batch.distribute`` action validates its payload and its
  applier marks the originating batch COMPLETED when the queue drains.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.reports.bulk_generation import generate_term_report_cards
from apps.reports.bulk_print import build_group_report_pdf, build_group_report_zip
from apps.reports.distribution_grouping import (
    GROUP_MODE_CLASS,
    GROUP_MODE_SPECIALTY,
    list_report_groups,
    resolve_group,
    resolve_report_group_mode,
    scoped_student_queryset,
)
from apps.reports.models import ReportCard, ReportCardBatch, TermPublishStatus
from apps.schools.models import School


def _one_page_pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=280)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


_ONE_PAGE = _one_page_pdf()


def _fake_render(request, template_name, context):
    return _ONE_PAGE


class BulkReportGroupingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Bulk Console School",
            slug="bulk-console-school",
            subdomain="bulk-console-school",
            country_code="CM",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name=Term.Name.FIRST,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(school=cls.school, name="Tech", code="TECH-BC")
        cls.spec_a = Specialty.objects.create(
            school=cls.school, department=dept, name="Electrical", code="ELEC-BC"
        )
        cls.spec_b = Specialty.objects.create(
            school=cls.school, department=dept, name="Mechanical", code="MECH-BC"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 4",
            code="F4-BC",
        )
        subject = Subject.objects.create(school=cls.school, name="Workshop")
        assignments = {}
        for spec in (cls.spec_a, cls.spec_b):
            assignments[spec.id] = SubjectAssignment.objects.create(
                school=cls.school,
                academic_year=cls.year,
                term=cls.term,
                classroom=cls.classroom,
                specialty=spec,
                subject=subject,
                coefficient=1,
            )
        teacher_user = User.objects.create_user(
            username="bc_teacher", password="x", role=User.Role.TEACHER
        )
        cls.teacher = TeacherProfile.objects.create(user=teacher_user, school=cls.school)
        AssessmentWeights.objects.create(
            school=cls.school, academic_year=cls.year, score_scale=20
        )
        TermPublishStatus.objects.create(
            academic_year=cls.year, term=cls.term, classroom=None, is_published=True
        )
        cls.student_a = cls._student("BC-A1", cls.spec_a)
        cls.student_b = cls._student("BC-B1", cls.spec_b)
        for student in (cls.student_a, cls.student_b):
            Evaluation.objects.create(
                school=cls.school,
                academic_year=cls.year,
                term=cls.term,
                subject_assignment=assignments[student.specialty_id],
                student=student,
                teacher=cls.teacher,
                seq1_score=Decimal("14.00"),
                seq2_score=Decimal("15.00"),
                exam_score=Decimal("16.00"),
            )

    @classmethod
    def _student(cls, code, specialty):
        return StudentProfile.objects.create(
            school=cls.school,
            first_name="Ako",
            last_name=code,
            student_code=code,
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=specialty,
            is_active=True,
        )

    # --- grouping resolver -------------------------------------------------
    def test_group_mode_defaults_to_class_for_base_school(self):
        base = School(name="B", school_type="BASE_SCHOOL")
        self.assertEqual(resolve_report_group_mode(base), GROUP_MODE_CLASS)

    def test_group_mode_is_specialty_for_technical_and_stem(self):
        for kind in ("TECHNICAL_COLLEGE", "STEM_ACADEMY"):
            with self.subTest(kind=kind):
                s = School(name="T", school_type=kind)
                self.assertEqual(resolve_report_group_mode(s), GROUP_MODE_SPECIALTY)

    def test_group_mode_config_override_wins_over_type(self):
        s = School(name="Override", school_type="BASE_SCHOOL", settings={"report_card_group_mode": "SPECIALTY"})
        self.assertEqual(resolve_report_group_mode(s), GROUP_MODE_SPECIALTY)

    def test_list_groups_by_specialty_counts_students(self):
        # When the school groups by specialty, both streams appear with live counts.
        self.school.school_type = "TECHNICAL_COLLEGE"
        self.school.save(update_fields=["school_type"])
        groups = list_report_groups(self.school, self.year)
        counts = {g["label"]: g["student_count"] for g in groups}
        self.assertEqual(counts.get("Electrical"), 1)
        self.assertEqual(counts.get("Mechanical"), 1)
        self.assertTrue(all(g["ref_kind"] == "specialty" for g in groups))

    def test_resolve_group_rejects_foreign_ref(self):
        ref, scope, label = resolve_group(self.school, self.year, GROUP_MODE_SPECIALTY, 999999)
        self.assertIsNone(scope)

    # --- shared scoping + specialty generation -----------------------------
    def test_scoped_queryset_filters_by_specialty(self):
        only_a = list(scoped_student_queryset(self.school, self.year, specialty=self.spec_a))
        self.assertEqual([s.student_code for s in only_a], ["BC-A1"])

    def test_generate_scopes_to_a_specialty(self):
        """The new capability: generate one stream's cards, not the whole class."""
        result = generate_term_report_cards(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            specialty=self.spec_a,
            actor=None,
            pdf_renderer=_fake_render,
        ).as_dict()
        self.assertEqual(result["generated"], 1, result["reasons"])
        self.assertTrue(ReportCard.objects.filter(student=self.student_a).exists())
        self.assertFalse(ReportCard.objects.filter(student=self.student_b).exists())

    # --- bulk print --------------------------------------------------------
    def test_print_merges_group_into_one_pdf(self):
        from pypdf import PdfReader

        students = scoped_student_queryset(self.school, self.year)
        data, res = build_group_report_pdf(
            school=self.school, students=students, academic_year=self.year,
            term=self.term, render_pdf=_fake_render,
        )
        self.assertEqual(res.included, 2, res.reasons)
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertEqual(len(PdfReader(io.BytesIO(data)).pages), 2)

    def test_print_zip_has_one_pdf_per_student(self):
        students = scoped_student_queryset(self.school, self.year, specialty=self.spec_a)
        data, res = build_group_report_zip(
            school=self.school, students=students, academic_year=self.year,
            term=self.term, render_pdf=_fake_render,
        )
        self.assertEqual(res.included, 1)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(len(zf.namelist()), 1)
            self.assertTrue(zf.namelist()[0].endswith(".pdf"))

    def test_print_skips_unpublished_group_and_returns_empty(self):
        TermPublishStatus.objects.all().delete()
        students = scoped_student_queryset(self.school, self.year)
        data, res = build_group_report_pdf(
            school=self.school, students=students, academic_year=self.year,
            term=self.term, render_pdf=_fake_render,
        )
        self.assertEqual(res.included, 0)
        self.assertEqual(data, b"")

    # --- offline distribute action ----------------------------------------
    def test_offline_payload_validation(self):
        from apps.platform_runtime.offline_action_types import validate_offline_payload

        self.assertTrue(validate_offline_payload("report_batch.distribute", {}))
        self.assertEqual(
            validate_offline_payload(
                "report_batch.distribute", {"academic_year_id": 1, "term_id": 2}
            ),
            [],
        )

    def test_applier_marks_batch_completed(self):
        from apps.platform_runtime.offline_queue import _apply_report_batch_distribute

        batch = ReportCardBatch.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            action=ReportCardBatch.Action.SHARE,
            status=ReportCardBatch.Status.QUEUED,
            group_mode=GROUP_MODE_SPECIALTY,
            group_ref_id=self.spec_a.id,
        )
        payload = {
            "academic_year_id": self.year.id,
            "term_id": self.term.id,
            "group_mode": GROUP_MODE_SPECIALTY,
            "group_ref_id": self.spec_a.id,
            "batch_id": batch.id,
        }
        with mock.patch(
            "apps.reports.bulk_distribution.distribute_report_batch",
            return_value={"ok": True, "students": 1, "notified": 1},
        ) as m:
            result = _apply_report_batch_distribute(self.school.id, self.teacher.user_id, payload)
        self.assertTrue(result["ok"])
        self.assertTrue(m.called)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ReportCardBatch.Status.COMPLETED)
        self.assertEqual(batch.included_count, 1)

    def test_applier_rejects_unresolvable_year(self):
        from apps.platform_runtime.offline_queue import _apply_report_batch_distribute

        result = _apply_report_batch_distribute(
            self.school.id, self.teacher.user_id,
            {"academic_year_id": 999999, "term_id": 999999},
        )
        self.assertFalse(result["ok"])


class BulkReportViewTests(TestCase):
    """View-layer coverage for the 4 bulk views — RBAC, ledger, offline messaging.

    RequestFactory + a superuser (bypasses ``@require_permission``); the heavy
    generate/print/distribute functions are mocked at the boundary so these
    exercise the VIEW logic (batch ledger creation, redirects, the offline
    QUEUED→COMPLETED message, the school=None guard) — the offline-first
    differentiator that otherwise had zero end-to-end coverage.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Bulk View School", slug="bulk-view-school",
            subdomain="bulk-view-school", country_code="CM", is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school, name="2025/2026",
            start_date=date(2025, 9, 1), end_date=date(2026, 7, 31), is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school, academic_year=cls.year, name=Term.Name.FIRST,
            position=1, start_date=date(2025, 9, 1), end_date=date(2025, 12, 15),
            is_active=True,
        )
        # A shared (school=None) year/term so the school=None guard is reachable.
        cls.shared_year = AcademicYear.objects.create(
            name="Shared 2025/2026", start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31), is_active=True,
        )
        cls.shared_term = Term.objects.create(
            academic_year=cls.shared_year, name=Term.Name.FIRST, position=1,
            start_date=date(2025, 9, 1), end_date=date(2025, 12, 15), is_active=True,
        )
        cls.admin = User.objects.create_superuser(
            username="bulk_view_admin", email="bv@example.com", password="x",
        )

    def _req(self, method, data=None, *, school="__self__"):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        req = getattr(RequestFactory(), method)("/reports/bulk/", data or {})
        req.school = self.school if school == "__self__" else school
        req.user = self.admin
        req.session = SessionStore()
        req._messages = FallbackStorage(req)
        return req

    def _data(self, **extra):
        return {"year": str(self.year.id), "term": str(self.term.id), **extra}

    def test_generate_view_creates_ledger_and_redirects(self):
        from apps.reports import views as reports_views
        from apps.reports.bulk_generation import BulkReportResult

        fake = BulkReportResult(generated=3, skipped=1, students=4)
        with mock.patch(
            "apps.reports.bulk_generation.generate_term_report_cards", return_value=fake
        ):
            resp = reports_views.bulk_report_generate(self._req("post", self._data()))
        self.assertEqual(resp.status_code, 302)
        batch = ReportCardBatch.objects.filter(action=ReportCardBatch.Action.GENERATE).first()
        self.assertIsNotNone(batch)
        self.assertEqual(batch.included_count, 3)
        self.assertEqual(batch.status, ReportCardBatch.Status.COMPLETED)

    def test_print_view_returns_pdf(self):
        from apps.reports import views as reports_views
        from apps.reports.bulk_print import GroupPrintResult

        with mock.patch(
            "apps.reports.bulk_print.build_group_report_pdf",
            return_value=(b"%PDF-1.4 merged", GroupPrintResult(included=2)),
        ):
            resp = reports_views.bulk_report_print(self._req("get", self._data(format="pdf")))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(".pdf", resp["Content-Disposition"])
        self.assertTrue(ReportCardBatch.objects.filter(action=ReportCardBatch.Action.PRINT).exists())

    def test_print_view_returns_zip(self):
        from apps.reports import views as reports_views
        from apps.reports.bulk_print import GroupPrintResult

        with mock.patch(
            "apps.reports.bulk_print.build_group_report_zip",
            return_value=(b"PKzipbytes", GroupPrintResult(included=1)),
        ):
            resp = reports_views.bulk_report_print(self._req("get", self._data(format="zip")))
        self.assertEqual(resp["Content-Type"], "application/zip")
        self.assertIn(".zip", resp["Content-Disposition"])

    def test_print_view_empty_group_redirects_with_warning(self):
        from apps.reports import views as reports_views
        from apps.reports.bulk_print import GroupPrintResult

        with mock.patch(
            "apps.reports.bulk_print.build_group_report_pdf",
            return_value=(b"", GroupPrintResult(included=0)),
        ):
            resp = reports_views.bulk_report_print(self._req("get", self._data()))
        self.assertEqual(resp.status_code, 302)  # redirect back, no file

    def test_share_view_enqueues_and_completes_when_online(self):
        from apps.reports import views as reports_views
        from apps.platform_runtime.models import OfflineAction

        with mock.patch(
            "apps.reports.bulk_distribution.distribute_report_batch",
            return_value={"ok": True, "students": 5, "notified": 5},
        ):
            resp = reports_views.bulk_report_share(self._req("post", self._data()))
        self.assertEqual(resp.status_code, 302)
        batch = ReportCardBatch.objects.filter(action=ReportCardBatch.Action.SHARE).first()
        self.assertIsNotNone(batch)
        # An offline action was durably enqueued...
        action = OfflineAction.objects.filter(
            school=self.school, action_type="report_batch.distribute"
        ).first()
        self.assertIsNotNone(action, "share did not enqueue the offline distribute action")
        # ...and the inline drain (online) completed it.
        batch.refresh_from_db()
        self.assertEqual(batch.status, ReportCardBatch.Status.COMPLETED)

    def test_share_view_forbidden_without_tenant_school(self):
        from apps.reports import views as reports_views

        # school=None but a shared year/term resolves → hits the school-context guard.
        resp = reports_views.bulk_report_share(
            self._req(
                "post",
                {"year": str(self.shared_year.id), "term": str(self.shared_term.id)},
                school=None,
            )
        )
        from django.http import HttpResponseForbidden

        self.assertIsInstance(resp, HttpResponseForbidden)
