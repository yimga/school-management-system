"""The grade-migration dry-run and the real apply must agree, and neither may
crash on a missing teacher.

Found by an A-Z audit follow-up (2026-07-16/17).

The migration wizard's grade path is dry_run -> apply:
  * dry-run:  ``migration_services.run_dry_run`` -> ``dry_run_grade_import``
  * apply:    ``views_migration`` -> ``preview_import`` + ``apply_import_from_preview``

Two defects made a green dry-run turn into a 500 on apply, every time:

1. ``dry_run_grade_import`` resolved the teacher with a DISCARDED expression::

       if teacher_username:
           TeacherProfile.objects.filter(user__username=teacher_username).first()

   The ``.first()`` result is thrown away, so a row with no usable teacher
   passed the dry-run clean ("would create N").

2. ``apply_import_from_preview`` built the teacher with a ternary that ALWAYS
   evaluated to ``None``::

       "teacher": teacher or assignment.teacher
       if hasattr(assignment, "teacher")
       else None,

   ``SubjectAssignment`` has NO ``teacher`` attribute (its relation is the
   ``teachers`` M2M / the ``teacher_assignments`` reverse FK), so
   ``hasattr(assignment, "teacher")`` is always False and the whole expression
   collapses to ``None`` -- the teacher resolved from the sheet is discarded.
   ``Evaluation.teacher`` is NOT NULL and ``Evaluation.save()`` calls
   ``full_clean()``, so this raised a ``ValidationError`` that
   ``views_migration``'s except tuple (ValueError/TypeError/.../RuntimeError,
   NOT ValidationError) did not catch -> the whole import 500'd on the first
   row.

So the operator saw "would create N" in the dry-run, clicked Apply, and got a
500 -- with zero grades imported. Nothing in the codebase exercised either
function before this file.
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
    apply_import_from_preview,
    dry_run_grade_import,
    preview_import,
)
from apps.evals.models import Evaluation, TeacherAssignment
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class GradeImportDryRunAndApplyAgreeTests(TestCase):

    def setUp(self):
        self.school = School.objects.create(
            name="Dry Run High", slug="dry-run-high", subdomain="dryrunhigh"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026", start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30), is_active=True, school=self.school,
        )
        self.term = Term.objects.create(
            name=Term.Name.FIRST, academic_year=self.year, position=1,
            start_date=date(2025, 9, 1), end_date=date(2025, 12, 1),
            school=self.school,
        )
        self.department = Department.objects.create(
            name="Science", code="SCI-DR", school=self.school
        )
        self.specialty = Specialty.objects.create(
            name="General", code="GEN-DR", department=self.department,
            school=self.school,
        )
        self.classroom = Classroom.objects.create(
            name="Form 1", code="F1-DR", academic_year=self.year,
            department=self.department, school=self.school,
        )
        self.subject = Subject.objects.create(name="Math DR", school=self.school)
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year, term=self.term, classroom=self.classroom,
            specialty=self.specialty, subject=self.subject, coefficient=1,
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Jo", last_name="Row",
            student_code="DR-1", academic_year=self.year,
            classroom=self.classroom, specialty=self.specialty,
        )

    # --- fixture helpers -------------------------------------------------

    def _teacher(self, username: str) -> TeacherProfile:
        return TeacherProfile.objects.create(
            user=User.objects.create_user(username=username, password="p"),
            school=self.school,
        )

    def _add_fallback_teacher(self) -> TeacherProfile:
        """A teacher who teaches this subject assignment (no sheet column)."""
        teacher = self._teacher("dr_fallback")
        TeacherAssignment.objects.create(
            teacher=teacher, academic_year=self.year,
            subject_assignment=self.assignment, school=self.school,
            is_active=True,
        )
        return teacher

    def _row(self, *, teacher_username: str = "") -> dict:
        return {
            "student_code": self.student.student_code,
            "subject_assignment_id": str(self.assignment.id),
            "term_id": str(self.term.id),
            "teacher_username": teacher_username,
            "seq1": "12", "seq2": "13", "exam": "14",
            "mock": "", "practical": "", "remarks": "",
        }

    def _apply(self, rows):
        preview = preview_import(rows)
        self.assertTrue(preview.is_valid, preview.errors)
        return apply_import_from_preview(preview, self.year)

    # --- apply ------------------------------------------------------------

    def test_apply_uses_the_assignment_teacher_when_the_sheet_omits_one(self):
        """The whole 500: a valid row with no teacher column.

        Before the fix the teacher ternary threw away every teacher, so
        Evaluation.save()'s full_clean() raised ValidationError on the required
        teacher and the import 500'd on this first row.
        """
        fallback = self._add_fallback_teacher()
        result = self._apply([self._row()])
        self.assertEqual(result["created"], 1, result.get("errors"))
        self.assertEqual(result["failed"], 0)
        ev = Evaluation.objects.get(
            student=self.student, subject_assignment=self.assignment,
            term=self.term,
        )
        self.assertEqual(
            ev.teacher_id, fallback.id,
            "with no teacher_username the row must adopt the subject "
            "assignment's own teacher, not crash on a null teacher",
        )

    def test_apply_uses_the_named_teacher_over_the_fallback(self):
        self._add_fallback_teacher()
        named = self._teacher("dr_named")
        result = self._apply([self._row(teacher_username="dr_named")])
        self.assertEqual(result["created"], 1, result.get("errors"))
        ev = Evaluation.objects.get(student=self.student, term=self.term)
        self.assertEqual(
            ev.teacher_id, named.id,
            "the teacher named on the sheet must win over the fallback",
        )

    def test_a_row_with_no_resolvable_teacher_is_counted_not_crashed(self):
        """No fallback teacher, no sheet column: honest failure, no 500."""
        result = self._apply([self._row()])  # must NOT raise
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(Evaluation.objects.count(), 0)
        self.assertIn("teacher", result["errors"][0]["error"])

    # --- dry-run / apply agreement ---------------------------------------

    def test_dry_run_flags_the_row_apply_would_reject(self):
        """The drift: dry-run said 'would create', apply 500'd.

        With no resolvable teacher the dry-run must report the failure the way
        apply will, not certify the row clean.
        """
        scorecard = dry_run_grade_import([self._row()], self.year)
        self.assertEqual(
            scorecard["created"], 0,
            "dry-run reported 'would create' for a row apply cannot persist -- "
            "the teacher lookup was a discarded expression",
        )
        self.assertGreaterEqual(scorecard["error_count"], 1)

    def test_dry_run_and_apply_agree_on_a_good_row(self):
        self._add_fallback_teacher()
        scorecard = dry_run_grade_import([self._row()], self.year)
        self.assertEqual(scorecard["created"], 1)
        self.assertEqual(scorecard["error_count"], 0)

        result = self._apply([self._row()])
        self.assertEqual(result["created"], 1, result.get("errors"))
        self.assertEqual(result["failed"], 0)
