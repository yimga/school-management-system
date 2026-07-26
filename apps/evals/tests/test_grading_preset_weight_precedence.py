"""M3: a scale PRESET formula must NOT silently override a school's CUSTOMIZED
AssessmentWeights.

Precedence proven here: explicit formula_text > customized weights > scale preset
(default weights). The bug was that a default GradingScale's preset formula fired
whenever the scale_type mapped to one, overriding weights a school set via the
granular UI.
"""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

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
from apps.evals.grade_computation import _weights_are_customized
from apps.evals.grading_formula_engine import PRESET_GRADING_FORMULAS
from apps.evals.models import AssessmentWeights, Evaluation, GradingScale
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class WeightsCustomizedPureTests(SimpleTestCase):
    def test_field_defaults_are_not_customized(self):
        self.assertFalse(_weights_are_customized(AssessmentWeights()))

    def test_changed_weight_is_customized(self):
        self.assertTrue(
            _weights_are_customized(
                AssessmentWeights(seq1_weight=25, seq2_weight=25, exam_weight=50)
            )
        )

    def test_none_is_not_customized(self):
        self.assertFalse(_weights_are_customized(None))


class PresetWeightPrecedenceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Precedence School", slug="prec-school", country_code="FR"
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
            username="prec-teacher", password="pass"
        )
        self.teacher_user.role = User.Role.TEACHER
        self.teacher_user.save(update_fields=["role"])
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, school=self.school
        )

    def _default_scale(self, config=None):
        return GradingScale.objects.create(
            school=self.school,
            code="local-default",
            name="FR 0-20",
            scale_type="numeric_0_20",  # maps to francophone_0_20 preset
            config=config or {},
            is_default=True,
            is_active=True,
        )

    def _weights(self, **overrides):
        base = dict(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            grading_scale="numeric_0_20",
            score_scale=20,
        )
        base.update(overrides)
        return AssessmentWeights.objects.create(**base)

    def _eval(self, seq1, seq2, exam):
        ev = Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            school=self.school,
            seq1_score=Decimal(str(seq1)),
            seq2_score=Decimal(str(seq2)),
            exam_score=Decimal(str(exam)),
        )
        ev.refresh_from_db()
        return ev

    def test_customized_weights_win_over_preset(self):
        # Scale has NO formula_text, so the francophone preset would fire — but the
        # school customized its weights (25/25/50 != 20/20/60), so they must win.
        self._default_scale(config={})
        self._weights(seq1_weight=25, seq2_weight=25, exam_weight=50)
        ev = self._eval(8, 12, 15)
        weighted = round((8 * 25 + 12 * 25 + 15 * 50) / 100, 2)  # 12.5
        preset = round(15 * 0.6 + (8 + 12) * 0.4, 2)  # 17.0
        self.assertNotEqual(weighted, preset)
        self.assertEqual(ev.total_score, weighted)  # honored the custom weights

    def test_default_weights_still_use_preset(self):
        # Same scale, but weights left at the field defaults (20/20/60): the school
        # never customized, so the scale preset legitimately drives the total.
        self._default_scale(config={})
        self._weights(seq1_weight=20, seq2_weight=20, exam_weight=60)
        ev = self._eval(8, 12, 15)
        preset = round(15 * 0.6 + (8 + 12) * 0.4, 2)  # 17.0
        weighted = round((8 * 20 + 12 * 20 + 15 * 60) / 100, 2)  # 13.0
        self.assertNotEqual(preset, weighted)
        self.assertEqual(ev.total_score, preset)  # unchanged behavior

    def test_explicit_formula_text_wins_even_with_customized_weights(self):
        # An explicit formula the school deliberately wrote overrides even custom weights.
        self._default_scale(config={"formula_text": PRESET_GRADING_FORMULAS["francophone_0_20"]})
        self._weights(seq1_weight=25, seq2_weight=25, exam_weight=50)
        ev = self._eval(8, 12, 15)
        formula = round(15 * 0.6 + (8 + 12) * 0.4, 2)  # 17.0
        self.assertEqual(ev.total_score, formula)  # explicit formula wins
