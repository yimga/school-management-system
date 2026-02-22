"""
Phase 8 Task 2: Advanced Analytics Tests
"""

import unittest
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()
from django.utils import timezone
from datetime import timedelta
from apps.analytics.models import GradeImportJob

try:
    from apps.analytics.models_extended import PerformanceMetrics
except Exception:
    PerformanceMetrics = None


class GradeImportJobTestCase(TestCase):
    """Test grade import tracking"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='teacher',
            password='pass123'
        )
    
    def test_create_import_job(self):
        """Test creating import job"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        ay = AcademicYear.objects.create(name='2025/2026', start_date=timezone.now().date(), end_date=timezone.now().date())
        term = Term.objects.create(academic_year=ay, name='FIRST', start_date=timezone.now().date(), end_date=timezone.now().date())

        job = GradeImportJob.objects.create(
            academic_year=ay,
            term=term,
            uploaded_by=self.user,
            status='completed',
            total_rows=100,
            created_count=100,
            failed_count=0
        )
        
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.created_count, 100)
    
    def test_import_job_tracking(self):
        """Test tracking import progress"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        ay = AcademicYear.objects.create(name='2025/2026', start_date=timezone.now().date(), end_date=timezone.now().date())
        term = Term.objects.create(academic_year=ay, name='FIRST', start_date=timezone.now().date(), end_date=timezone.now().date())

        job = GradeImportJob.objects.create(
            academic_year=ay,
            term=term,
            uploaded_by=self.user,
            status='processing',
            total_rows=50
        )
        
        # Update progress
        job.created_count = 25
        job.save()
        
        self.assertEqual(job.created_count, 25)
    
    def test_import_job_error_handling(self):
        """Test error tracking during import"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        ay = AcademicYear.objects.create(name='2025/2026', start_date=timezone.now().date(), end_date=timezone.now().date())
        term = Term.objects.create(academic_year=ay, name='FIRST', start_date=timezone.now().date(), end_date=timezone.now().date())

        job = GradeImportJob.objects.create(
            academic_year=ay,
            term=term,
            uploaded_by=self.user,
            status='partial',
            total_rows=100,
            created_count=95,
            failed_count=5,
            error_log=[
                {'row': 50, 'error': 'Invalid grade value'},
                {'row': 75, 'error': 'Student not found'},
            ]
        )
        
        self.assertEqual(len(job.error_log), 2)
        self.assertEqual(job.failed_count, 5)


@unittest.skip("PerformanceMetrics table removed in migration 0007")
class AdvancedAnalyticsTestCase(TestCase):
    """Test advanced analytics functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='student',
            password='pass123'
        )
    
    def test_performance_metrics_creation(self):
        """Test creating performance metrics"""
        from apps.people.models import StudentProfile
        from apps.academics.models import AcademicYear, Department, Classroom, Specialty
        from django.utils import timezone

        dept = Department.objects.create(name='Science', code='SCI')
        ay = AcademicYear.objects.create(name='2025/2026', start_date=timezone.now().date(), end_date=timezone.now().date())
        classroom = Classroom.objects.create(academic_year=ay, department=dept, name='Form 1A', code='F1A')
        specialty = Specialty.objects.create(department=dept, name='General', code='GEN')

        student_profile = StudentProfile.objects.create(
            first_name='Test',
            last_name='Student',
            admission_number='STU001',
            academic_year=ay,
            classroom=classroom,
            specialty=specialty
        )
        
        metrics = PerformanceMetrics.objects.create(
            student=student_profile,
            average_score=75.5,
            total_evaluations=10,
            pass_rate=100.0,
            trend='STABLE',
            risk_level='LOW'
        )
        
        self.assertEqual(metrics.average_score, 75.5)
        self.assertEqual(metrics.risk_level, 'LOW')
    
    def test_risk_level_assessment(self):
        """Test risk level calculation"""
        from apps.people.models import StudentProfile
        
        from apps.academics.models import AcademicYear, Department, Classroom, Specialty
        from django.utils import timezone

        dept = Department.objects.create(name='Science', code='SCI')
        ay = AcademicYear.objects.create(name='2025/2026', start_date=timezone.now().date(), end_date=timezone.now().date())
        classroom = Classroom.objects.create(academic_year=ay, department=dept, name='Form 2A', code='F2A')
        specialty = Specialty.objects.create(department=dept, name='General', code='GEN')

        student_profile = StudentProfile.objects.create(
            first_name='Test2',
            last_name='Student2',
            admission_number='STU002',
            academic_year=ay,
            classroom=classroom,
            specialty=specialty
        )
        
        # Low risk
        metrics_low = PerformanceMetrics.objects.create(
            student=student_profile,
            average_score=80.0,
            risk_level='LOW'
        )
        self.assertEqual(metrics_low.risk_level, 'LOW')
        
        # High risk
        student2 = User.objects.create_user(username='student2', password='pass')
        # Create profile for student2
        classroom2 = Classroom.objects.create(academic_year=ay, department=dept, name='Form 3A', code='F3A')
        profile2 = StudentProfile.objects.create(first_name='High', last_name='Risk', admission_number='STU003', academic_year=ay, classroom=classroom2, specialty=specialty)
        
        metrics_high = PerformanceMetrics.objects.create(
            student=profile2,
            average_score=35.0,
            risk_level='CRITICAL'
        )
        self.assertEqual(metrics_high.risk_level, 'CRITICAL')
        self.assertEqual(metrics_low.risk_level, 'LOW')
        



class AnalyticsQueryTestCase(TestCase):
    """Test analytics queries"""
    
    def test_bulk_import_job_queries(self):
        """Test querying multiple import jobs"""
        from django.utils import timezone
        from apps.academics.models import AcademicYear, Term

        user = User.objects.create_user(username='analytics_bulk_%s' % id(self), password='pass')
        ay = AcademicYear.objects.create(name='2025/2026', start_date=timezone.now().date(), end_date=timezone.now().date())
        term = Term.objects.create(academic_year=ay, name='FIRST', start_date=timezone.now().date(), end_date=timezone.now().date())
        
        for i in range(5):
            GradeImportJob.objects.create(
                academic_year=ay,
                term=term,
                uploaded_by=user,
                status='completed'
            )
        
        jobs = GradeImportJob.objects.filter(status='completed')
        self.assertEqual(jobs.count(), 5)
