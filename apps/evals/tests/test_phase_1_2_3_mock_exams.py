"""
Tests for Phase 1.2.3: Mock Exam Support
Tests mock exam configuration, blending algorithm, and integration with ranking system.
"""

from datetime import timedelta

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import IntegrityError

from apps.academics.models import AcademicYear, Term, Classroom, Department
from apps.evals.models import MockExamSetting
from apps.evals.mock_exams import (
    calculate_blended_score,
    should_use_mock_blending,
)
from apps.evals.ranking import (
    RankingCache,
    get_class_ranking,
    get_school_ranking,
)


class MockExamSettingModelTests(TestCase):
    """Test MockExamSetting model creation, validation, and queries."""

    def setUp(self):
        """Set up test fixtures."""
        self.department = Department.objects.create(
            name="General Education",
            code="GEN",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2024/2025",
            start_date=timezone.now().date(),
            # end_date must be strictly AFTER start_date: the
            # academicyear_end_after_start CHECK constraint (academics/0084)
            # rejects a same-day year, which is what these fixtures created.
            end_date=timezone.now().date() + timedelta(days=300),
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        # Create unique classrooms for each test to avoid unique constraint violations
        self.classrooms = [
            Classroom.objects.create(
                name=f"FORM 5{chr(65 + i)}",
                code=f"F5{chr(65 + i)}",
                academic_year=self.academic_year,
                department=self.department,
            )
            for i in range(7)
        ]
        self.classroom_idx = 0

    def _get_next_classroom(self):
        """Get next unique classroom for this test."""
        classroom = self.classrooms[self.classroom_idx]
        self.classroom_idx += 1
        return classroom

    def test_create_mock_exam_setting_with_defaults(self):
        """Test creating MockExamSetting with default values."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
        )
        self.assertEqual(setting.final_weight, 70)
        self.assertEqual(setting.mock_weight, 30)
        self.assertFalse(setting.is_active)
        self.assertIsNotNone(setting.classroom)

    def test_create_mock_exam_setting_custom_weights(self):
        """Test creating MockExamSetting with custom weights."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=60,
            mock_weight=40,
            is_active=True,
        )
        self.assertEqual(setting.final_weight, 60)
        self.assertEqual(setting.mock_weight, 40)
        self.assertTrue(setting.is_active)

    def test_validation_weights_must_sum_to_100_when_active(self):
        """Test that weights must sum to 100% when is_active=True."""
        setting = MockExamSetting(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=60,
            mock_weight=30,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            setting.full_clean()

    def test_validation_allows_non_100_sum_when_inactive(self):
        """Test that weight validation is skipped when is_active=False."""
        setting = MockExamSetting(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=50,
            mock_weight=40,
            is_active=False,
        )
        setting.full_clean()
        self.assertFalse(setting.is_active)

    def test_unique_constraint(self):
        """Test unique constraint on (academic_year, classroom, term)."""
        classroom = self._get_next_classroom()
        MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=classroom,
            term=self.term,
            is_active=True,
        )
        # Attempting to create another with same (academic_year, classroom, term) violates unique
        with self.assertRaises((IntegrityError, ValidationError)):
            MockExamSetting.objects.create(
                academic_year=self.academic_year,
                classroom=classroom,
                term=self.term,
                is_active=False,
            )

    def test_get_for_creates_with_defaults(self):
        """Test get_for() class method creates with defaults."""
        classroom = self._get_next_classroom()
        setting = MockExamSetting.get_for(self.academic_year, classroom, self.term)
        self.assertEqual(setting.final_weight, 70)
        self.assertEqual(setting.mock_weight, 30)
        self.assertFalse(setting.is_active)
        self.assertEqual(setting.classroom, classroom)

    def test_get_for_returns_existing(self):
        """Test get_for() returns existing setting instead of creating."""
        classroom = self._get_next_classroom()
        created = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=classroom,
            term=self.term,
            final_weight=80,
            mock_weight=20,
            is_active=True,
        )
        retrieved = MockExamSetting.get_for(self.academic_year, classroom, self.term)
        self.assertEqual(retrieved.id, created.id)
        self.assertEqual(retrieved.final_weight, 80)


class CalculateBlendedScoreTests(TestCase):
    """Test calculate_blended_score() function."""

    def setUp(self):
        """Set up test fixtures."""
        self.department = Department.objects.create(
            name="General Education",
            code="GEN",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2024/2025",
            start_date=timezone.now().date(),
            # end_date must be strictly AFTER start_date: the
            # academicyear_end_after_start CHECK constraint (academics/0084)
            # rejects a same-day year, which is what these fixtures created.
            end_date=timezone.now().date() + timedelta(days=300),
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        self.classrooms = [
            Classroom.objects.create(
                name=f"FORM 7{chr(65 + i)}",
                code=f"F7{chr(65 + i)}",
                academic_year=self.academic_year,
                department=self.department,
            )
            for i in range(8)
        ]
        self.classroom_idx = 0

    def _get_next_classroom(self):
        """Get next unique classroom for this test."""
        classroom = self.classrooms[self.classroom_idx]
        self.classroom_idx += 1
        return classroom

    def test_blending_with_valid_scores(self):
        """Test blending calculation with valid final and mock scores."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=70,
            mock_weight=30,
            is_active=True,
        )
        result = calculate_blended_score(70.0, 16.0, setting)
        self.assertEqual(result, 53.8)

    def test_blending_with_integer_scores(self):
        """Test blending with integer input (should handle type conversion)."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=70,
            mock_weight=30,
            is_active=True,
        )
        result = calculate_blended_score(18, 14, setting)
        self.assertEqual(result, 16.8)

    def test_blending_when_inactive_returns_final(self):
        """Test that blending returns final score when setting is inactive."""
        setting_inactive = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=70,
            mock_weight=30,
            is_active=False,
        )
        result = calculate_blended_score(75.0, 68.0, setting_inactive)
        self.assertEqual(result, 75.0)

    def test_blending_with_none_mock_score_returns_final(self):
        """Test that blending returns final when mock_score is None."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=70,
            mock_weight=30,
            is_active=True,
        )
        result = calculate_blended_score(75.0, None, setting)
        self.assertEqual(result, 75.0)

    def test_blending_with_none_final_score_returns_zero(self):
        """Test that blending returns 0.0 when final_score is None."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=70,
            mock_weight=30,
            is_active=True,
        )
        result = calculate_blended_score(None, 70.0, setting)
        self.assertEqual(result, 0.0)

    def test_blending_with_edge_case_scores(self):
        """Test blending with edge case scores (0 and 20)."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=70,
            mock_weight=30,
            is_active=True,
        )
        result = calculate_blended_score(0, 20, setting)
        self.assertEqual(result, 6.0)

        result = calculate_blended_score(20, 0, setting)
        self.assertEqual(result, 14.0)

    def test_blending_custom_weights(self):
        """Test blending with custom weights."""
        setting_custom = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=60,
            mock_weight=40,
            is_active=True,
        )
        result = calculate_blended_score(15.0, 18.0, setting_custom)
        self.assertEqual(result, 16.2)

    def test_blending_decimal_result_rounding(self):
        """Test that blending results are rounded to 2 decimal places."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self._get_next_classroom(),
            term=self.term,
            final_weight=70,
            mock_weight=30,
            is_active=True,
        )
        result = calculate_blended_score(13.0, 11.0, setting)
        self.assertEqual(result, 12.4)
        self.assertIsInstance(result, float)


class ShouldUseMockBlendingTests(TestCase):
    """Test should_use_mock_blending() detection logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.department = Department.objects.create(
            name="General Education",
            code="GEN",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2024/2025",
            start_date=timezone.now().date(),
            # end_date must be strictly AFTER start_date: the
            # academicyear_end_after_start CHECK constraint (academics/0084)
            # rejects a same-day year, which is what these fixtures created.
            end_date=timezone.now().date() + timedelta(days=300),
        )

    def test_detect_form5_by_name(self):
        """Test FORM 5 detection by classroom name."""
        classroom = Classroom.objects.create(
            name="FORM 5A",
            code="OTHER",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_form7_by_name(self):
        """Test FORM 7 detection by classroom name."""
        classroom = Classroom.objects.create(
            name="FORM 7B",
            code="OTHER",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_upper6_by_name(self):
        """Test UPPER 6 detection by classroom name."""
        classroom = Classroom.objects.create(
            name="UPPER 6",
            code="OTHER",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_formvi_by_name(self):
        """Test FORM VI (Roman numerals) detection."""
        classroom = Classroom.objects.create(
            name="FORM VI",
            code="OTHER",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_formvii_by_name(self):
        """Test FORM VII (Roman numerals) detection."""
        classroom = Classroom.objects.create(
            name="FORM VII",
            code="OTHER",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_form5_by_code(self):
        """Test FORM 5 detection by code."""
        classroom = Classroom.objects.create(
            name="GENERIC",
            code="F5",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_form7_by_code(self):
        """Test FORM 7 detection by code."""
        classroom = Classroom.objects.create(
            name="GENERIC",
            code="F7",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_upper6_by_code(self):
        """Test UPPER 6 detection by code."""
        classroom = Classroom.objects.create(
            name="GENERIC",
            code="U6",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_detect_a2_by_code(self):
        """Test A2 (Advanced Level 2) detection by code."""
        classroom = Classroom.objects.create(
            name="GENERIC",
            code="A2",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_no_detection_for_lower_forms(self):
        """Test that lower forms are not detected."""
        classroom = Classroom.objects.create(
            name="FORM 1",
            code="F1",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertFalse(should_use_mock_blending(classroom))

    def test_no_detection_for_form3(self):
        """Test that FORM 3 is not detected."""
        classroom = Classroom.objects.create(
            name="FORM 3",
            code="F3",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertFalse(should_use_mock_blending(classroom))

    def test_case_insensitive_name_detection(self):
        """Test that detection is case-insensitive."""
        classroom = Classroom.objects.create(
            name="form 5a",
            code="OTHER",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))

    def test_case_insensitive_code_detection(self):
        """Test that code detection is case-insensitive."""
        classroom = Classroom.objects.create(
            name="GENERIC",
            code="f5",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.assertTrue(should_use_mock_blending(classroom))


class RankingWithMockBlendingTests(TestCase):
    """Test ranking system integration with mock exam blending."""

    def setUp(self):
        """Set up test fixtures."""
        self.department = Department.objects.create(
            name="General Education",
            code="GEN",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2024/2025",
            start_date=timezone.now().date(),
            # end_date must be strictly AFTER start_date: the
            # academicyear_end_after_start CHECK constraint (academics/0084)
            # rejects a same-day year, which is what these fixtures created.
            end_date=timezone.now().date() + timedelta(days=300),
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        self.classroom = Classroom.objects.create(
            name="FORM 5A",
            code="F5A",
            academic_year=self.academic_year,
            department=self.department,
        )

    def test_ranking_cache_key_includes_mock_suffix(self):
        """Test that cache keys include :mock suffix for mock-blended rankings (and tenant prefix)."""
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix

        prefix = get_tenant_cache_prefix(None)
        cache_key_standard = RankingCache.get_cache_key(
            self.term, self.classroom, use_mock_blending=False
        )
        cache_key_mock = RankingCache.get_cache_key(
            self.term, self.classroom, use_mock_blending=True
        )

        self.assertEqual(
            cache_key_standard,
            f"{prefix}:ranking:term:{self.term.id}:class:{self.classroom.id}",
        )
        self.assertEqual(
            cache_key_mock,
            f"{prefix}:ranking:term:{self.term.id}:class:{self.classroom.id}:mock",
        )
        self.assertNotEqual(cache_key_standard, cache_key_mock)

    def test_get_class_ranking_accepts_use_mock_blending(self):
        """Test get_class_ranking function accepts use_mock_blending parameter."""
        result_standard = get_class_ranking(
            self.classroom, self.term, use_mock_blending=False
        )
        self.assertIsInstance(result_standard, list)

        result_with_blending = get_class_ranking(
            self.classroom, self.term, use_mock_blending=True
        )
        self.assertIsInstance(result_with_blending, list)

    def test_get_school_ranking_accepts_use_mock_blending(self):
        """Test get_school_ranking function accepts use_mock_blending parameter."""
        result_standard = get_school_ranking(self.term, use_mock_blending=False)
        self.assertIsInstance(result_standard, list)

        result_with_blending = get_school_ranking(self.term, use_mock_blending=True)
        self.assertIsInstance(result_with_blending, list)

    def test_ranking_cache_invalidates_both_variants(self):
        """Test that invalidating cache clears both standard and mock-blended."""
        RankingCache.invalidate(self.term, self.classroom)


class MockBlendingIntegrationTests(TestCase):
    """Integration tests for complete mock exam workflow."""

    def setUp(self):
        """Set up complete test environment."""
        self.department = Department.objects.create(
            name="General Education",
            code="GEN",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2024/2025",
            start_date=timezone.now().date(),
            # end_date must be strictly AFTER start_date: the
            # academicyear_end_after_start CHECK constraint (academics/0084)
            # rejects a same-day year, which is what these fixtures created.
            end_date=timezone.now().date() + timedelta(days=300),
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        self.form5_classroom = Classroom.objects.create(
            name="FORM 5A",
            code="F5A",
            academic_year=self.academic_year,
            department=self.department,
        )
        self.form1_classroom = Classroom.objects.create(
            name="FORM 1A",
            code="F1A",
            academic_year=self.academic_year,
            department=self.department,
        )

    def test_form5_detected_automatically(self):
        """Test that FORM 5 classroom is detected automatically."""
        self.assertTrue(should_use_mock_blending(self.form5_classroom))

    def test_form1_not_detected(self):
        """Test that FORM 1 classroom is not detected."""
        self.assertFalse(should_use_mock_blending(self.form1_classroom))

    def test_mock_setting_retrieved_for_form5(self):
        """Test MockExamSetting retrieval for FORM 5."""
        setting = MockExamSetting.get_for(
            self.academic_year, self.form5_classroom, self.term
        )
        self.assertEqual(setting.classroom, self.form5_classroom)
        self.assertEqual(setting.academic_year, self.academic_year)

    def test_mock_blending_with_updated_weights(self):
        """Test blending with non-default weights."""
        setting = MockExamSetting.objects.create(
            academic_year=self.academic_year,
            classroom=self.form5_classroom,
            term=self.term,
            final_weight=80,
            mock_weight=20,
            is_active=True,
        )
        result = calculate_blended_score(18, 15, setting)
        self.assertEqual(result, 17.4)


class MockExamCacheStrategyTests(TestCase):
    """Test cache strategy separation for mock-blended rankings."""

    def setUp(self):
        """Set up test fixtures."""
        self.department = Department.objects.create(
            name="General Education",
            code="GEN",
        )
        self.academic_year = AcademicYear.objects.create(
            name="2024/2025",
            start_date=timezone.now().date(),
            # end_date must be strictly AFTER start_date: the
            # academicyear_end_after_start CHECK constraint (academics/0084)
            # rejects a same-day year, which is what these fixtures created.
            end_date=timezone.now().date() + timedelta(days=300),
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        self.classroom = Classroom.objects.create(
            name="FORM 5A",
            code="F5A",
            academic_year=self.academic_year,
            department=self.department,
        )

    def test_cache_keys_are_unique_per_variant(self):
        """Test that cache keys are unique for standard vs mock-blended."""
        key1 = RankingCache.get_cache_key(self.term, self.classroom, False)
        key2 = RankingCache.get_cache_key(self.term, self.classroom, True)

        self.assertNotEqual(key1, key2)
        self.assertNotIn(":mock", key1)
        self.assertIn(":mock", key2)

    def test_school_wide_cache_keys_include_mock_suffix(self):
        """Test school-wide cache keys also get :mock suffix."""
        key1 = RankingCache.get_cache_key(self.term, None, False)
        key2 = RankingCache.get_cache_key(self.term, None, True)

        self.assertNotEqual(key1, key2)
        self.assertNotIn(":mock", key1)
        self.assertIn(":mock", key2)
