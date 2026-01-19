from decimal import Decimal

from django.test import TestCase

from apps.academics.models import AcademicYear, Term, Subject, Classroom, SubjectAssignment
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile


class EvaluationScoreTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(name="2025/2026")
        self.term = Term.objects.create(name=Term.Name.FIRST, academic_year=self.year)
        self.classroom = Classroom.objects.create(name="Form 1", academic_year=self.year)
        self.subject = Subject.objects.create(name="Math")
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            subject=self.subject,
            coefficient=1,
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            academic_year=self.year,
            classroom=self.classroom,
        )
        self.teacher = TeacherProfile.objects.create(first_name="T", last_name="Teacher")

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

        # Expected: (10*20 + 15*20 + 18*60) / 100 = 15.6
        self.assertEqual(evaluation.total_score, 15.6)

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

        # Expected: (12*40 + 16*60) / 100 = 14.4
        self.assertEqual(evaluation.total_score, 14.4)
