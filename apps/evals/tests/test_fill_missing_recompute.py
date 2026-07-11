"""Regression: the marks-grid "Fill missing scores" bulk action must recompute
the denormalized ``final_score`` / ``normalized_value``.

``final_score`` is a stored column populated only inside ``Evaluation.save()``
and read (as the stored value) by class/school rankings (``Avg("final_score")``),
the degree-audit credit check, the EWS grade-drop detector, and frozen
transcripts. The bulk fill action used to write the raw score columns via a
queryset ``.update()``, which bypasses ``save()`` and leaves ``final_score``
frozen at its pre-fill (incomplete) value forever. ``_apply_fill_missing`` now
persists via ``save()`` so the stored value stays consistent.

``test_raw_update_leaves_final_score_stale`` documents the exact bug the fix
closes (a raw ``.update()`` desyncs the stored column); the other two prove the
fix recomputes and that an out-of-range fill is surfaced, not silently written.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

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
from apps.evals.models import AssessmentWeights, Evaluation
from apps.evals.views import _apply_fill_missing
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class FillMissingRecomputeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Fill Test School", slug="fill-test", country_code="FR"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=self.school,
        )
        self.term = Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=self.year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(
            name="Science", code="SCI", school=self.school
        )
        self.specialty = Specialty.objects.create(
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            name="Form 1",
            code="F1",
            academic_year=self.year,
            department=self.department,
            school=self.school,
        )
        self.subject = Subject.objects.create(name="Math", school=self.school)
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1,
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="STD001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            school=self.school,
        )
        self.teacher_user = User.objects.create_user(
            username="fill-teacher", password="pass"
        )
        self.teacher_user.role = User.Role.TEACHER
        self.teacher_user.save(update_fields=["role"])
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, school=self.school
        )
        AssessmentWeights.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            seq1_weight=20,
            seq2_weight=20,
            exam_weight=60,
            grading_scale="numeric_0_20",
            score_scale=20,
        )
        self.fields = ["seq1_score", "seq2_score", "exam_score"]

    def _make_eval_missing_exam(self):
        # seq1 + seq2 present, exam missing → final_score reflects the incomplete
        # component set until the exam mark is filled in.
        return Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            school=self.school,
            seq1_score=Decimal("8"),
            seq2_score=Decimal("12"),
            exam_score=None,
        )

    def test_apply_fill_missing_recomputes_final_score(self):
        ev = self._make_eval_missing_exam()
        before = ev.final_score

        changed = _apply_fill_missing(ev, Decimal("20"), self.fields)
        self.assertTrue(changed)

        ev.refresh_from_db()
        # The exam mark landed...
        self.assertEqual(ev.exam_score, Decimal("20"))
        # ...and the stored final_score was recomputed to match the live property
        # (no stale denormalized value), and actually moved off its pre-fill value.
        self.assertIsNotNone(ev.final_score)
        self.assertEqual(float(ev.final_score), ev.total_score)
        self.assertNotEqual(ev.final_score, before)
        # normalized_value tracks final_score (never left stale-None post-fill).
        self.assertIsNotNone(ev.normalized_value)

    def test_apply_fill_missing_noop_when_nothing_missing(self):
        ev = Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            school=self.school,
            seq1_score=Decimal("8"),
            seq2_score=Decimal("12"),
            exam_score=Decimal("15"),
        )
        self.assertFalse(_apply_fill_missing(ev, Decimal("20"), self.fields))

    def test_raw_update_leaves_final_score_stale(self):
        """Documents the bug the fix closes: a queryset .update() desyncs the
        stored final_score from the live total_score."""
        ev = self._make_eval_missing_exam()
        Evaluation.objects.filter(id=ev.id).update(exam_score=Decimal("20"))
        ev.refresh_from_db()
        # The raw column moved, but the denormalized final_score did NOT — it is
        # now stale relative to the recomputed total_score. This is exactly what
        # every stored-column reader would see forever under the old code path.
        self.assertEqual(ev.exam_score, Decimal("20"))
        self.assertNotEqual(float(ev.final_score), ev.total_score)

    def test_out_of_range_fill_raises_validation_error(self):
        ev = self._make_eval_missing_exam()
        # 999 exceeds every grading scale (20 / 100 / 4) → save()'s full_clean()
        # rejects it; the helper propagates so the view can count it as skipped.
        with self.assertRaises(ValidationError):
            _apply_fill_missing(ev, Decimal("999"), self.fields)
