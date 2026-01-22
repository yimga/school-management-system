"""
Phase 1.2.2: Ranking Enhancement Tests

Test tie handling, caching, and query optimization.
"""

from django.test import TestCase
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.academics.models import AcademicYear, Term, Classroom, Subject, SubjectAssignment, Department, Specialty
from apps.people.models import StudentProfile, TeacherProfile
from apps.evals.models import Evaluation
from apps.evals.ranking import (
    RankingCache,
    get_class_ranking,
    get_school_ranking,
    get_student_rank,
    get_rank_position_with_context,
)


class RankingTieHandlingTest(TestCase):
    """Test tie handling in rankings."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with tied students."""
        cls.year = AcademicYear.objects.create(
            name="2024/2025",
            start_date="2024-01-01",
            end_date="2025-12-31",
        )
        cls.term = Term.objects.create(
            academic_year=cls.year,
            name="FIRST",
            start_date="2024-01-01",
            end_date="2024-04-30",
        )
        cls.department = Department.objects.create(
            name="General",
            code="GEN",
        )
        cls.classroom = Classroom.objects.create(
            academic_year=cls.year,
            department=cls.department,
            name="Form 1A",
            code="F1A",
        )

        # Create specialty
        cls.specialty = Specialty.objects.create(
            department=cls.department,
            name="General",
            code="GSPEC",
        )

        # Create teacher for evaluations
        from apps.accounts.models import User
        user_teacher = User.objects.create_user(username="testteacher", password="pass123", first_name="Teacher", last_name="Test")
        cls.teacher = TeacherProfile.objects.create(
            user=user_teacher,
        )

        # Create subjects
        cls.math = Subject.objects.create(name="Mathematics")
        cls.english = Subject.objects.create(name="English Language")

        # Create subject assignments (with required fields)
        cls.math_assign = SubjectAssignment.objects.create(
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=cls.math,
            coefficient=2.0,
        )
        cls.english_assign = SubjectAssignment.objects.create(
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=cls.english,
            coefficient=1.0,
        )

        # Create students
        cls.student_top = StudentProfile.objects.create(
            first_name="Charlie",
            last_name="Chen",
            student_code="STU003",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )
        cls.student_tied1 = StudentProfile.objects.create(
            first_name="Alice",
            last_name="Anderson",
            student_code="STU001",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )
        cls.student_tied2 = StudentProfile.objects.create(
            first_name="Bob",
            last_name="Brown",
            student_code="STU002",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )
        cls.student_low = StudentProfile.objects.create(
            first_name="Diana",
            last_name="Davis",
            student_code="STU004",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )

        # Create evaluations
        # Top student: 17 average (18 Math + 16 English)
        Evaluation.objects.create(
            student=cls.student_top,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=18,
            exam_score=18,
            teacher=cls.teacher,
        )
        Evaluation.objects.create(
            student=cls.student_top,
            subject_assignment=cls.english_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=16,
            exam_score=16,
            teacher=cls.teacher,
        )

        # Tied 1: 15 average (16 Math + 13 English)
        Evaluation.objects.create(
            student=cls.student_tied1,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=16,
            exam_score=16,
            teacher=cls.teacher,
        )
        Evaluation.objects.create(
            student=cls.student_tied1,
            subject_assignment=cls.english_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=13,
            exam_score=13,
            teacher=cls.teacher,
        )

        # Tied 2: 15 average (same as Tied 1)
        Evaluation.objects.create(
            student=cls.student_tied2,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=16,
            exam_score=16,
            teacher=cls.teacher,
        )
        Evaluation.objects.create(
            student=cls.student_tied2,
            subject_assignment=cls.english_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=13,
            exam_score=13,
            teacher=cls.teacher,
        )

        # Low student: 12 average (14 Math + 10 English)
        Evaluation.objects.create(
            student=cls.student_low,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=14,
            exam_score=14,
            teacher=cls.teacher,
        )
        Evaluation.objects.create(
            student=cls.student_low,
            subject_assignment=cls.english_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=10,
            exam_score=10,
            teacher=cls.teacher,
        )

    def setUp(self):
        """Clear cache before each test."""
        cache.clear()

    def test_ranking_order(self):
        """Test ranking order with ties."""
        rankings = get_class_ranking(self.classroom, self.term)

        self.assertEqual(len(rankings), 4)
        # Should be: Charlie (rank 1, avg 85), Alice & Bob (rank 2, avg 75), Diana (rank 4, avg 65)
        self.assertEqual(rankings[0].rank, 1)
        self.assertEqual(rankings[0].student.id, self.student_top.id)
        self.assertEqual(rankings[1].rank, 2)
        self.assertEqual(rankings[2].rank, 2)
        self.assertEqual(rankings[3].rank, 4)

    def test_tie_detection(self):
        """Test that ties are properly detected."""
        rankings = get_class_ranking(self.classroom, self.term)

        tied_entries = [r for r in rankings if r.is_tied]
        self.assertEqual(len(tied_entries), 2)  # Both tied students

        for entry in tied_entries:
            self.assertEqual(entry.tied_count, 2)

    def test_deterministic_ranking(self):
        """Test that ranking is deterministic."""
        ranking1 = get_class_ranking(self.classroom, self.term, use_cache=False)
        ranking2 = get_class_ranking(self.classroom, self.term, use_cache=False)

        for e1, e2 in zip(ranking1, ranking2):
            self.assertEqual(e1.student.id, e2.student.id)
            self.assertEqual(e1.rank, e2.rank)


class RankingCachingTest(TestCase):
    """Test caching behavior."""

    @classmethod
    def setUpTestData(cls):
        """Create minimal test data."""
        cls.year = AcademicYear.objects.create(
            name="2024/2025",
            start_date="2024-01-01",
            end_date="2025-12-31",
        )
        cls.term = Term.objects.create(
            academic_year=cls.year,
            name="FIRST",
            start_date="2024-01-01",
            end_date="2024-04-30",
        )
        cls.department = Department.objects.create(name="General", code="GEN")
        cls.classroom = Classroom.objects.create(
            academic_year=cls.year,
            department=cls.department,
            name="Form 1A",
            code="F1A",
        )
        cls.specialty = Specialty.objects.create(
            department=cls.department,
            name="General",
            code="GSPEC",
        )

        cls.math = Subject.objects.create(name="Mathematics")
        cls.math_assign = SubjectAssignment.objects.create(
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=cls.math,
            coefficient=1.0,
        )

        cls.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="STU001",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )

        Evaluation.objects.create(
            student=cls.student,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=16,
            exam_score=16,
            teacher=cls.student,
        )

    def setUp(self):
        """Clear cache before each test."""
        cache.clear()

    def test_ranking_caching(self):
        """Test that rankings are cached."""
        ranking1 = get_class_ranking(self.classroom, self.term)
        self.assertEqual(len(ranking1), 1)

        cache_key = RankingCache.get_cache_key(self.term, self.classroom)
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached), 1)

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        ranking1 = get_class_ranking(self.classroom, self.term)
        self.assertEqual(len(ranking1), 1)

        RankingCache.invalidate(self.term, self.classroom)

        cache_key = RankingCache.get_cache_key(self.term, self.classroom)
        cached = cache.get(cache_key)
        self.assertIsNone(cached)

    def test_cache_keys_differ(self):
        """Test that school and class rankings use different cache keys."""
        class_ranking = get_class_ranking(self.classroom, self.term)
        school_ranking = get_school_ranking(self.term)

        class_key = RankingCache.get_cache_key(self.term, self.classroom)
        school_key = RankingCache.get_cache_key(self.term, None)

        self.assertNotEqual(class_key, school_key)
        self.assertIsNotNone(cache.get(class_key))
        self.assertIsNotNone(cache.get(school_key))


class RankingPositionTest(TestCase):
    """Test student position queries."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.year = AcademicYear.objects.create(
            name="2024/2025",
            start_date="2024-01-01",
            end_date="2025-12-31",
        )
        cls.term = Term.objects.create(
            academic_year=cls.year,
            name="FIRST",
            start_date="2024-01-01",
            end_date="2024-04-30",
        )
        cls.department = Department.objects.create(name="General", code="GEN")
        cls.classroom = Classroom.objects.create(
            academic_year=cls.year,
            department=cls.department,
            name="Form 1A",
            code="F1A",
        )
        cls.specialty = Specialty.objects.create(
            department=cls.department,
            name="General",
            code="GSPEC",
        )

        cls.math = Subject.objects.create(name="Mathematics")
        cls.math_assign = SubjectAssignment.objects.create(
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=cls.math,
            coefficient=1.0,
        )

        # Create 3 students
        cls.student_top = StudentProfile.objects.create(
            first_name="Top",
            last_name="Student",
            student_code="STU001",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )
        cls.student_mid = StudentProfile.objects.create(
            first_name="Mid",
            last_name="Student",
            student_code="STU002",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )
        cls.student_low = StudentProfile.objects.create(
            first_name="Low",
            last_name="Student",
            student_code="STU003",
            is_active=True,
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
        )

        # Create evaluations
        Evaluation.objects.create(
            student=cls.student_top,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=18,
            exam_score=18,
            teacher=cls.student_top,
        )
        Evaluation.objects.create(
            student=cls.student_mid,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=15,
            exam_score=15,
            teacher=cls.student_mid,
        )
        Evaluation.objects.create(
            student=cls.student_low,
            subject_assignment=cls.math_assign,
            academic_year=cls.year,
            term=cls.term,
            seq1_score=12,
            exam_score=12,
            teacher=cls.student_low,
        )

    def setUp(self):
        """Clear cache."""
        cache.clear()

    def test_get_student_rank(self):
        """Test getting individual student rank."""
        top_rank = get_student_rank(self.student_top, self.term, self.classroom)
        mid_rank = get_student_rank(self.student_mid, self.term, self.classroom)
        low_rank = get_student_rank(self.student_low, self.term, self.classroom)

        self.assertEqual(top_rank, 1)
        self.assertEqual(mid_rank, 2)
        self.assertEqual(low_rank, 3)

    def test_get_rank_position_context(self):
        """Test getting full rank context."""
        context = get_rank_position_with_context(self.student_top, self.term)

        self.assertEqual(context['class_rank'], 1)
        self.assertEqual(context['school_rank'], 1)
        self.assertEqual(context['class_size'], 3)
        self.assertEqual(context['school_size'], 3)
        self.assertFalse(context['is_tied'])
        self.assertEqual(context['average'], 90.0)
