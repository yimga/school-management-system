"""
Phase 8 Task 2: Advanced Analytics Tests
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.analytics.models import BenchmarkAggregate, GradeImportJob

User = get_user_model()


class GradeImportJobTestCase(TestCase):
    """Test grade import tracking"""

    def setUp(self):
        self.user = User.objects.create_user(username="teacher", password="pass123")

    def test_create_import_job(self):
        """Test creating import job"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        ay = AcademicYear.objects.create(
            name="2025/2026",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        term = Term.objects.create(
            academic_year=ay,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )

        job = GradeImportJob.objects.create(
            academic_year=ay,
            term=term,
            uploaded_by=self.user,
            status="completed",
            total_rows=100,
            created_count=100,
            failed_count=0,
        )

        self.assertEqual(job.status, "completed")
        self.assertEqual(job.created_count, 100)

    def test_import_job_tracking(self):
        """Test tracking import progress"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        ay = AcademicYear.objects.create(
            name="2025/2026",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        term = Term.objects.create(
            academic_year=ay,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )

        job = GradeImportJob.objects.create(
            academic_year=ay,
            term=term,
            uploaded_by=self.user,
            status="processing",
            total_rows=50,
        )

        # Update progress
        job.created_count = 25
        job.save()

        self.assertEqual(job.created_count, 25)

    def test_import_job_error_handling(self):
        """Test error tracking during import"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        ay = AcademicYear.objects.create(
            name="2025/2026",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        term = Term.objects.create(
            academic_year=ay,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )

        job = GradeImportJob.objects.create(
            academic_year=ay,
            term=term,
            uploaded_by=self.user,
            status="partial",
            total_rows=100,
            created_count=95,
            failed_count=5,
            error_log=[
                {"row": 50, "error": "Invalid grade value"},
                {"row": 75, "error": "Student not found"},
            ],
        )

        self.assertEqual(len(job.error_log), 2)
        self.assertEqual(job.failed_count, 5)


class AdvancedAnalyticsTestCase(TestCase):
    """Test advanced analytics functionality."""

    def setUp(self):
        self.user = User.objects.create_user(username="student", password="pass123")

    def test_benchmark_aggregate_creation(self):
        """Test creating anonymized benchmark aggregates."""
        metric = BenchmarkAggregate.objects.create(
            region_code="CMR",
            sub_system="GENERAL",
            subject_id=101,
            term_id=1,
            academic_year_id=2026,
            metric="avg_score",
            value="75.5000",
            sample_size=120,
        )
        self.assertEqual(metric.region_code, "CMR")
        self.assertEqual(metric.sub_system, "GENERAL")
        self.assertEqual(str(metric.value), "75.5000")
        self.assertEqual(metric.sample_size, 120)

    def test_benchmark_aggregate_region_and_metric_queries(self):
        """Test benchmark rollups can be filtered by region and metric."""
        BenchmarkAggregate.objects.create(
            region_code="CMR",
            sub_system="GENERAL",
            metric="avg_score",
            value="74.0000",
            sample_size=90,
        )
        BenchmarkAggregate.objects.create(
            region_code="CMR",
            sub_system="GENERAL",
            metric="pass_rate",
            value="0.8400",
            sample_size=90,
        )
        BenchmarkAggregate.objects.create(
            region_code="USA",
            sub_system="GENERAL",
            metric="avg_score",
            value="82.0000",
            sample_size=140,
        )

        cmr_avg = BenchmarkAggregate.objects.filter(
            region_code="CMR", metric="avg_score"
        )
        usa_any = BenchmarkAggregate.objects.filter(region_code="USA")
        self.assertEqual(cmr_avg.count(), 1)
        self.assertEqual(str(cmr_avg.first().value), "74.0000")
        self.assertEqual(usa_any.count(), 1)


class AnalyticsQueryTestCase(TestCase):
    """Test analytics queries"""

    def test_bulk_import_job_queries(self):
        """Test querying multiple import jobs"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        user = User.objects.create_user(
            username="analytics_bulk_%s" % id(self), password="pass"
        )
        ay = AcademicYear.objects.create(
            name="2025/2026",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )
        term = Term.objects.create(
            academic_year=ay,
            name="FIRST",
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )

        for i in range(5):
            GradeImportJob.objects.create(
                academic_year=ay, term=term, uploaded_by=user, status="completed"
            )

        jobs = GradeImportJob.objects.filter(status="completed")
        self.assertEqual(jobs.count(), 5)
