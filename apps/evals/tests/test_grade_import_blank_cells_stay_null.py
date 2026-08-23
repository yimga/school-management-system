"""A blank grade-sheet cell must import as NULL, not as a mark of zero.

``apply_import`` coerced seq1/seq2/exam with ``Decimal(str(row.get("seq1") or 0))``
while the very next lines used the correct ``... if row.get("mock") else None``
idiom for mock/practical -- the None idiom was applied to two of the five
components.

The damage is the loss of the missing/zero distinction. A school importing
sequence-1 marks in October leaves the exam column blank because the exam has
not been sat; every row then lands with ``exam_score = 0``, so
``is_complete_for_ranking`` reports the row as fully marked, the compliance
dashboard shows the class as complete, and ``_apply_fill_missing`` (which fills
only components that are ``None``) will never touch it. The mark is
indistinguishable from a genuine zero for the rest of the year.

The same coercion sat in the dry-run preview (``preview_import`` and
``preview_import_with_validation``), so preview and apply agreed and nothing
surfaced the loss.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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
from apps.evals.importers import (
    apply_import,
    apply_import_from_preview,
    preview_import,
    preview_import_with_validation,
)
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class BlankImportCellsStayNullTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Blank Cell High", slug="blank-cell", subdomain="blank-cell"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-blank",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=self.school,
        )
        self.term = Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=self.year,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            school=self.school,
        )
        self.department = Department.objects.create(
            name="Science", code="SCI-BLANK", school=self.school
        )
        self.specialty = Specialty.objects.create(
            name="General", code="GEN-BLANK", department=self.department,
            school=self.school,
        )
        self.classroom = Classroom.objects.create(
            name="Form 1", code="F1-BLANK", academic_year=self.year,
            department=self.department, school=self.school,
        )
        self.subject = Subject.objects.create(name="Math Blank", school=self.school)
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year, term=self.term, classroom=self.classroom,
            specialty=self.specialty, subject=self.subject, coefficient=1,
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Blank",
            student_code="BLK-1", academic_year=self.year,
            classroom=self.classroom, specialty=self.specialty,
        )
        self.teacher = TeacherProfile.objects.create(
            user=User.objects.create_user(username="blank_teacher", password="p"),
            school=self.school,
        )
        # seq1/seq2/exam all weighted: the exam is a REQUIRED component, so a
        # blank exam cell must keep the row visibly incomplete.
        AssessmentWeights.objects.create(
            academic_year=self.year, term=self.term, classroom=self.classroom,
            seq1_weight=30, seq2_weight=30, exam_weight=40,
            mock_weight=0, practical_weight=0, score_scale=20,
        )

    def _row(self, **overrides) -> dict:
        row = {
            "student_code": self.student.student_code,
            "subject_assignment_id": str(self.assignment.id),
            "term_id": str(self.term.id),
            "teacher_username": self.teacher.user.username,
            "seq1": "18",
            "seq2": "17",
            "exam": "",          # not sat yet -- the October import
            "mock": "",
            "practical": "",
            "remarks": "",
        }
        row.update(overrides)
        return row

    # --- apply_import (csv-rows path) ------------------------------------

    def test_apply_import_leaves_a_blank_exam_null(self) -> None:
        result = apply_import([self._row()], academic_year=self.year)
        # Guard against a vacuous pass: the row must actually have landed.
        self.assertEqual(result["failed"], 0, result["errors"])
        self.assertEqual(result["created"], 1)

        evaluation = Evaluation.objects.get(student=self.student, term=self.term)
        self.assertEqual(evaluation.seq1_score, Decimal("18"))
        self.assertIsNone(
            evaluation.exam_score,
            "a blank exam cell imported as a mark of zero -- indistinguishable "
            "from a genuine 0 for the rest of the year",
        )

    def test_a_blank_exam_keeps_the_row_incomplete(self) -> None:
        """The consequence: the compliance / fill-missing readers."""
        apply_import([self._row()], academic_year=self.year)
        evaluation = Evaluation.objects.get(student=self.student, term=self.term)
        self.assertFalse(
            evaluation.is_complete_for_ranking,
            "exam_score=0 makes the class report as fully marked and hides the "
            "row from _apply_fill_missing forever",
        )

    def test_an_explicit_zero_still_writes_zero(self) -> None:
        """Only a BLANK cell becomes NULL -- a real 0 must survive."""
        apply_import([self._row(exam="0")], academic_year=self.year)
        evaluation = Evaluation.objects.get(student=self.student, term=self.term)
        self.assertEqual(evaluation.exam_score, Decimal("0"))
        self.assertTrue(evaluation.is_complete_for_ranking)

    # --- preview_import -> apply_import_from_preview (migration path) -----

    def test_preview_import_carries_the_blank_through_as_none(self) -> None:
        preview = preview_import([self._row()])
        self.assertTrue(preview.is_valid, preview.errors)
        self.assertEqual(preview.rows[0].seq1, 18.0)
        self.assertIsNone(preview.rows[0].exam)

    def test_apply_from_preview_leaves_a_blank_exam_null(self) -> None:
        preview = preview_import([self._row()])
        result = apply_import_from_preview(preview, self.year)
        self.assertEqual(result["failed"], 0, result["errors"])
        self.assertEqual(result["created"], 1)

        evaluation = Evaluation.objects.get(student=self.student, term=self.term)
        self.assertIsNone(evaluation.exam_score)

    # --- preview_import_with_validation (the UI dry run) ------------------

    def test_validated_preview_agrees_with_apply(self) -> None:
        rows, errors = preview_import_with_validation([self._row()])
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].seq1, 18.0)
        self.assertIsNone(
            rows[0].exam,
            "the dry run showed exam=0 and the apply then wrote 0, so preview "
            "and apply agreed on the wrong value and nothing surfaced the loss",
        )
