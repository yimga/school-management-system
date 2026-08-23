"""An unparseable grade cell must fail its OWN row, not the whole import.

Regression guard for the blank-cell fix. Routing every score column through
``_optional_decimal`` replaced ``float(row.get("seq1") or 0)`` with
``Decimal(text)`` -- and ``Decimal("abc")`` raises ``decimal.InvalidOperation``,
which derives from ``ArithmeticError``, NOT from ``ValueError``. Every guard on
this pipeline is typed on ``ValueError``/``TypeError``:

* ``preview_import``'s own ``except (ValueError, TypeError)`` per row,
* ``_EVALS_IMPORTERS_ROW_ERRORS``, used by ``apply_import`` and
  ``preview_import_with_validation`` per row,
* the migration wizard's ``except`` in ``apps/accounts/views_migration.py``,
  which turns a caught failure into "Grade import failed. Details: ..." on the
  page instead of a 500.

So one typo in one cell of one row escaped all three: the whole batch aborted
and the wizard 500'd, where before the change ``float("abc")`` raised
``ValueError`` and the row was reported and skipped.

The fix keeps the Decimal parse (blank still means missing, "0" still means
zero) but re-raises an unparseable cell as ``ValueError`` at the single
chokepoint, so every existing caller's guard applies again.
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
    _optional_decimal,
    apply_import,
    preview_import,
    preview_import_with_validation,
)
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class UnparseableCellIsARowFailureTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Typo High", slug="typo-high", subdomain="typo-high"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-typo",
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
            name="Science", code="SCI-TYPO", school=self.school
        )
        self.specialty = Specialty.objects.create(
            name="General", code="GEN-TYPO", department=self.department,
            school=self.school,
        )
        self.classroom = Classroom.objects.create(
            name="Form 1", code="F1-TYPO", academic_year=self.year,
            department=self.department, school=self.school,
        )
        self.subject = Subject.objects.create(name="Math Typo", school=self.school)
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year, term=self.term, classroom=self.classroom,
            specialty=self.specialty, subject=self.subject, coefficient=1,
            school=self.school,
        )
        self.good_student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Good",
            student_code="TYPO-OK", academic_year=self.year,
            classroom=self.classroom, specialty=self.specialty,
        )
        self.bad_student = StudentProfile.objects.create(
            school=self.school, first_name="Bea", last_name="Typo",
            student_code="TYPO-BAD", academic_year=self.year,
            classroom=self.classroom, specialty=self.specialty,
        )
        self.teacher = TeacherProfile.objects.create(
            user=User.objects.create_user(username="typo_teacher", password="p"),
            school=self.school,
        )
        AssessmentWeights.objects.create(
            academic_year=self.year, term=self.term, classroom=self.classroom,
            seq1_weight=30, seq2_weight=30, exam_weight=40,
            mock_weight=0, practical_weight=0, score_scale=20,
        )

    def _row(self, student, **overrides) -> dict:
        row = {
            "student_code": student.student_code,
            "subject_assignment_id": str(self.assignment.id),
            "term_id": str(self.term.id),
            "teacher_username": self.teacher.user.username,
            "seq1": "18",
            "seq2": "17",
            "exam": "16",
            "mock": "",
            "practical": "",
            "remarks": "",
        }
        row.update(overrides)
        return row

    # --- the chokepoint contract -----------------------------------------

    def test_unparseable_cell_raises_the_error_type_the_callers_guard_on(self) -> None:
        """``InvalidOperation`` is an ArithmeticError, so no caller caught it."""
        with self.assertRaises(ValueError):
            _optional_decimal("18,5")

    def test_the_parse_itself_is_unchanged(self) -> None:
        """Guard against a vacuous pass: this must not weaken blank/zero."""
        self.assertIsNone(_optional_decimal(""))
        self.assertIsNone(_optional_decimal(None))
        self.assertEqual(_optional_decimal("0"), Decimal("0"))
        self.assertEqual(_optional_decimal(" 18.5 "), Decimal("18.5"))

    # --- preview_import (the migration wizard's dry run) ------------------

    def test_preview_import_reports_the_bad_row_and_keeps_the_good_one(self) -> None:
        preview = preview_import(
            [self._row(self.good_student), self._row(self.bad_student, seq1="18,5")]
        )
        # The batch survived at all -- before the fix this call raised.
        self.assertEqual(len(preview.rows), 1)
        self.assertEqual(preview.rows[0].student_code, "TYPO-OK")
        self.assertEqual(len(preview.errors), 1)
        self.assertIn("Row 2", preview.errors[0])

    # --- apply_import (the real write) ------------------------------------

    def test_apply_import_counts_the_bad_row_as_failed_and_writes_the_good_one(
        self,
    ) -> None:
        result = apply_import(
            [self._row(self.good_student), self._row(self.bad_student, exam="n/a")],
            academic_year=self.year,
        )
        self.assertEqual(result["failed"], 1, result["errors"])
        self.assertEqual(result["errors"][0]["student_code"], "TYPO-BAD")
        # The consequence, not just the counter: one typo must not cost the
        # whole batch. Before the fix the exception escaped the per-row guard,
        # so NOTHING in the file landed.
        self.assertEqual(result["created"], 1)
        self.assertTrue(
            Evaluation.objects.filter(student=self.good_student, term=self.term).exists()
        )
        self.assertFalse(
            Evaluation.objects.filter(student=self.bad_student, term=self.term).exists()
        )

    # --- preview_import_with_validation (the evals UI dry run) ------------

    def test_validated_preview_reports_the_bad_row_and_keeps_the_good_one(self) -> None:
        rows, errors = preview_import_with_validation(
            [self._row(self.good_student), self._row(self.bad_student, seq2="??")]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].student_code, "TYPO-OK")
        self.assertEqual(len(errors), 1)
        self.assertIn("Row 3", errors[0])
