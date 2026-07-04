"""Regression: report-card preview must not 500 on a tenant with no students.

Production 500 (2026-07-04, new-school.runmycampus.com):
    GET /siteconfig/reports/preview/academic-authority/term/pdf/
    TypeError: Field 'id' expected a number but got
        namespace(id=0, last_name='Sample', first_name='Learner', ...)

When a fresh tenant has no active students, ``_resolve_preview_student`` falls
back to ``_mock_preview_student()`` (a ``SimpleNamespace``). If an active
academic year + term exist, ``_build_report_context_for_pdf`` /
``reportcard_style_preview`` used to hand that mock straight to
``term_report_context`` / ``annual_report_context``, which do
``Evaluation.objects.filter(student=<mock>, ...)`` — a non-model receiver on an
FK lookup raises the ``TypeError`` above. The fix gates the real-data branch on
``_is_real_student`` so the mock renders the sample preview instead.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.people.models import StudentProfile
from apps.reports.models import ReportCard
from apps.siteconfig import views


class IsRealStudentTests(SimpleTestCase):
    def test_mock_preview_student_is_not_real(self):
        self.assertFalse(views._is_real_student(views._mock_preview_student()))

    def test_unsaved_student_profile_is_not_real(self):
        self.assertFalse(views._is_real_student(StudentProfile()))

    def test_namespace_with_pk_is_not_real(self):
        # Has a pk but is not a StudentProfile -> must not reach the ORM.
        self.assertFalse(views._is_real_student(SimpleNamespace(pk=5)))

    def test_persisted_student_profile_is_real(self):
        # pk set (no DB round-trip needed) + correct type -> real.
        self.assertTrue(views._is_real_student(StudentProfile(pk=5)))


class BuildReportContextEmptyTenantTests(SimpleTestCase):
    """With active year+term but a mock student, the DB-querying context
    builders must NOT be called — the sample preview branch handles it."""

    def _patches(self, term_ctx, annual_ctx):
        site = SimpleNamespace(get_brand_metadata=lambda: {})
        return (
            mock.patch.object(
                views, "get_active_year_and_term", return_value=(object(), object())
            ),
            mock.patch.object(views, "get_effective_site_settings", return_value=site),
            mock.patch.object(views, "resolve_report_labels", return_value={}),
            mock.patch.object(views, "term_report_context", side_effect=term_ctx),
            mock.patch.object(views, "annual_report_context", side_effect=annual_ctx),
        )

    def test_term_preview_does_not_touch_db_for_mock_student(self):
        boom = AssertionError("term_report_context must not run for a mock student")
        p = self._patches(term_ctx=boom, annual_ctx=boom)
        with p[0], p[1], p[2], p[3] as term_ctx, p[4]:
            context = views._build_report_context_for_pdf(
                style=SimpleNamespace(),
                report_type=ReportCard.Type.TERM,
                student=views._mock_preview_student(),
            )
        term_ctx.assert_not_called()
        self.assertTrue(context["preview_mode"])
        self.assertEqual(context["rows"], [])  # sample fallback, no evaluations
        self.assertEqual(context["student_name"], "Sample Learner")

    def test_annual_preview_does_not_touch_db_for_mock_student(self):
        boom = AssertionError("annual_report_context must not run for a mock student")
        p = self._patches(term_ctx=boom, annual_ctx=boom)
        with p[0], p[1], p[2], p[3], p[4] as annual_ctx:
            context = views._build_report_context_for_pdf(
                style=SimpleNamespace(),
                report_type=ReportCard.Type.ANNUAL,
                student=views._mock_preview_student(),
            )
        annual_ctx.assert_not_called()
        self.assertTrue(context["preview_mode"])
