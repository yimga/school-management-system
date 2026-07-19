"""Prove evaluate_grading_formula is wired into the live Evaluation.total_score path."""

from datetime import date
from decimal import Decimal

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
from apps.evals.grading_formula_engine import PRESET_GRADING_FORMULAS
from apps.evals.models import AssessmentWeights, Evaluation, GradingScale
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class GradingFormulaLivePathTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Formula Test School",
            slug="formula-test",
            country_code="FR",
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
            username="formula-teacher", password="pass"
        )
        self.teacher_user.role = User.Role.TEACHER
        self.teacher_user.save(update_fields=["role"])
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, school=self.school
        )

    def test_total_score_uses_grading_scale_formula_not_weighted_mean(self):
        formula = PRESET_GRADING_FORMULAS["francophone_0_20"]
        GradingScale.objects.create(
            school=self.school,
            code="local-default",
            name="FR 0-20",
            scale_type="numeric_0_20",
            config={"formula_text": formula},
            is_default=True,
            is_active=True,
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
        evaluation = Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            school=self.school,
            seq1_score=Decimal("10"),
            seq2_score=Decimal("10"),
            exam_score=Decimal("15"),
        )
        # Formula: min(20, max(0, exam*0.6 + coursework*0.4)) with coursework=20 → 13.0
        # Weighted mean would be (10*20 + 10*20 + 15*60)/100 = 13.0 — same here;
        # use asymmetric scores to distinguish paths.
        evaluation.seq1_score = Decimal("8")
        evaluation.seq2_score = Decimal("12")
        evaluation.exam_score = Decimal("15")
        evaluation.save()
        evaluation.refresh_from_db()
        expected = round(15 * 0.6 + (8 + 12) * 0.4, 2)  # 17.0
        weighted_mean = round((8 * 20 + 12 * 20 + 15 * 60) / 100, 2)  # 13.0
        self.assertNotEqual(expected, weighted_mean)
        self.assertEqual(evaluation.total_score, expected)
        self.assertEqual(float(evaluation.final_score), expected)

    def test_signal_sets_letter_from_formula_total(self):
        GradingScale.objects.create(
            school=self.school,
            code="local-default",
            name="FR 0-20",
            scale_type="numeric_0_20",
            config={
                "formula_text": PRESET_GRADING_FORMULAS["francophone_0_20"],
            },
            is_default=True,
            is_active=True,
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
            grade_a_min=Decimal("16"),
            grade_b_min=Decimal("14"),
            grade_c_min=Decimal("12"),
            grade_d_min=Decimal("10"),
        )
        evaluation = Evaluation.objects.create(
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
        evaluation.refresh_from_db()
        self.assertEqual(evaluation.letter_grade, "A")

    def test_waec_preset_key_drives_total_without_formula_text(self):
        """Polymorphic path: scale_type alone selects PRESET_GRADING_FORMULAS."""
        from apps.evals.grade_computation import _SCALE_TYPE_TO_PRESET_KEY

        GradingScale.objects.create(
            school=self.school,
            code="waec-default",
            name="WAEC",
            scale_type="waec_letter",
            config={},  # no formula_text — must resolve via preset map
            is_default=True,
            is_active=True,
        )
        AssessmentWeights.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            seq1_weight=20,
            seq2_weight=20,
            exam_weight=60,
            grading_scale="waec_letter",
            score_scale=100,
        )
        evaluation = Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            school=self.school,
            seq1_score=Decimal("40"),
            seq2_score=Decimal("40"),
            exam_score=Decimal("80"),
        )
        evaluation.refresh_from_db()
        # waec_aggregate: round((exam + coursework) / 2) = round((80+80)/2) = 80
        weighted_mean = round((40 * 20 + 40 * 20 + 80 * 60) / 100, 2)  # 64.0
        self.assertEqual(_SCALE_TYPE_TO_PRESET_KEY["waec_letter"], "waec_aggregate")
        self.assertEqual(evaluation.total_score, 80.0)
        self.assertNotEqual(evaluation.total_score, weighted_mean)

    def test_every_scale_type_maps_to_a_preset(self):
        from apps.evals.grade_computation import _SCALE_TYPE_TO_PRESET_KEY
        from apps.evals.models import GradingScale

        for scale_type, _label in GradingScale.ScaleType.choices:
            preset = _SCALE_TYPE_TO_PRESET_KEY.get(scale_type)
            self.assertTrue(preset, msg=f"missing preset map for {scale_type}")
            self.assertIn(preset, PRESET_GRADING_FORMULAS)
