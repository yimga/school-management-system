"""Derived-value lineage — record-level provenance for computed outputs.

Locks the 9.8 lineage wave (2026-07-02). Before it, derived values (report-card
averages, nightly at-risk scores) were persisted with ZERO record of their
inputs — you could not ask "which Evaluation rows produced this report card".
These tests assert the lineage model roundtrip, the honest granularity
contract (row vs scope), input capping, best-effort never-raises behavior,
that term_report_context exposes the exact Evaluation rows it read, and that
the ReportCard stamp writes row-level lineage from that context.
"""

from __future__ import annotations

from datetime import date

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
from apps.evals.models import Evaluation
from apps.metadata.models_derived_lineage import (
    DerivedValueLineage,
    lineage_for,
    record_derived_lineage,
    risk_scope_inputs,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.reports.models import ReportCard
from apps.reports.services import term_report_context
from apps.reports.views import _record_report_card_lineage
from apps.schools.models import School


class DerivedLineageModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Lineage School", slug="lineage-a", subdomain="lineage-a"
        )

    def _output(self):
        year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
        )
        student = StudentProfile.objects.create(
            school=self.school,
            first_name="Lin",
            last_name="Model",
            student_code="LIN000",
            academic_year=year,
            is_active=True,
        )
        return ReportCard.objects.create(
            school=self.school,
            academic_year=year,
            student=student,
            type=ReportCard.Type.ANNUAL,
        )

    def test_record_and_query_roundtrip(self):
        output = self._output()
        record_derived_lineage(
            output=output,
            computation="report_card.term",
            inputs=[{"model": "evals.Evaluation", "pk": "1"}],
        )
        rows = list(lineage_for(output))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].output_model, "reports.ReportCard")
        self.assertEqual(rows[0].granularity, "row")
        self.assertEqual(rows[0].school_id, self.school.pk)
        self.assertFalse(rows[0].inputs_truncated)

    def test_inputs_capped_and_flagged(self):
        output = self._output()
        entry = record_derived_lineage(
            output=output,
            computation="report_card.term",
            inputs=[{"model": "evals.Evaluation", "pk": str(i)} for i in range(650)],
        )
        self.assertEqual(len(entry.inputs), 500)
        self.assertTrue(entry.inputs_truncated)

    def test_record_is_best_effort(self):
        self.assertIsNone(
            record_derived_lineage(output=object(), computation="x", inputs=[])
        )
        self.assertEqual(DerivedValueLineage.objects.count(), 0)

    def test_risk_scope_inputs_shape(self):
        inputs = risk_scope_inputs(42, 30, "v3")
        models = {i["model"] for i in inputs}
        self.assertIn("evals.Evaluation", models)
        self.assertIn("analytics.MLModel", models)
        self.assertEqual(
            [i for i in inputs if i["model"] == "evals.Evaluation"][0]["scope"],
            {"student": "42", "window_days": 30},
        )


class ReportCardLineageWiringTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Lineage School B", slug="lineage-b", subdomain="lineage-b"
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 5),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(
            school=self.school, name="Science", code="SCI-LIN"
        )
        specialty = Specialty.objects.create(
            school=self.school, department=department, name="General", code="GEN-LIN"
        )
        self.specialty = specialty
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=department,
            name="Form 1A",
            code="F1A-LIN",
        )
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=specialty,
            subject=subject,
            coefficient=2,
        )
        teacher_user = User.objects.create_user(
            username="lineage_teacher", password="pass123", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=teacher_user, school=self.school
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Lin",
            last_name="Eage",
            student_code="LIN001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            is_active=True,
        )
        self.evaluation = Evaluation.objects.create(
            student=self.student,
            subject_assignment=self.subject_assignment,
            teacher=self.teacher,
            academic_year=self.year,
            term=self.term,
            seq1_score=14,
            seq2_score=16,
        )

    def test_term_context_exposes_evaluation_ids(self):
        context = term_report_context(self.student, self.year, self.term)
        self.assertEqual(
            context.get("lineage_evaluation_ids"), [self.evaluation.pk]
        )

    def test_report_card_stamp_writes_row_lineage(self):
        context = term_report_context(self.student, self.year, self.term)
        rc = ReportCard.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            student=self.student,
            type=ReportCard.Type.TERM,
        )
        _record_report_card_lineage(rc, context)
        entry = lineage_for(rc).get()
        self.assertEqual(entry.computation, "report_card.term")
        self.assertEqual(entry.granularity, "row")
        self.assertEqual(
            entry.inputs,
            [{"model": "evals.Evaluation", "pk": str(self.evaluation.pk)}],
        )

    def test_annual_stamp_records_scope(self):
        rc = ReportCard.objects.create(
            school=self.school,
            academic_year=self.year,
            student=self.student,
            type=ReportCard.Type.ANNUAL,
        )
        _record_report_card_lineage(rc, {})
        entry = lineage_for(rc).get()
        self.assertEqual(entry.computation, "report_card.annual")
        self.assertEqual(entry.granularity, "scope")
        self.assertEqual(entry.inputs[0]["model"], "evals.Evaluation")
        self.assertEqual(
            entry.inputs[0]["scope"]["student"], str(self.student.pk)
        )
