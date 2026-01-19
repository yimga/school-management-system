from decimal import Decimal
from datetime import date

from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Term,
    Subject,
    Classroom,
    SubjectAssignment,
    Department,
    Specialty,
)
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile


class EvaluationScoreTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=self.year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(name="General", code="GEN", department=self.department)
        self.classroom = Classroom.objects.create(
            name="Form 1",
            code="F1",
            academic_year=self.year,
            department=self.department,
        )
        self.subject = Subject.objects.create(name="Math")
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1,
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="STD001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.teacher_user = User.objects.create_user(username="teacher", password="pass")
        self.teacher_user.role = User.Role.TEACHER
        self.teacher_user.save(update_fields=["role"])
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user)

    def test_total_score_respects_weights(self):
        AssessmentWeights.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            seq1_weight=20,
            seq2_weight=20,
            exam_weight=60,
            mock_weight=0,
            practical_weight=0,
            score_scale=20,
        )

        evaluation = Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("10"),
            seq2_score=Decimal("15"),
            exam_score=Decimal("18"),
        )

        # (10*20 + 15*20 + 18*60) / 100 = 15.8
        self.assertEqual(evaluation.total_score, 15.8)

    def test_total_score_handles_missing_components(self):
        AssessmentWeights.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            seq1_weight=0,
            seq2_weight=40,
            exam_weight=60,
            mock_weight=0,
            practical_weight=0,
            score_scale=20,
        )

        evaluation = Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            seq2_score=Decimal("12"),
            exam_score=Decimal("16"),
        )

        # (12*40 + 16*60) / 100 = 14.4
        self.assertEqual(evaluation.total_score, 14.4)
