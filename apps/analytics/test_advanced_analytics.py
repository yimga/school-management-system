"""
Phase 8 Task 2: Advanced Analytics Tests
"""

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from apps.analytics.models_extended import GradeImportJob, PerformanceMetrics


class GradeImportJobTestCase(TestCase):
    """Test grade import tracking"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='teacher',
            password='pass123'
        )
    
    def test_create_import_job(self):
        """Test creating import job"""
        job = GradeImportJob.objects.create(
            created_by=self.user,
            file_name='grades_2026_01.csv',
            status='COMPLETED',
            total_records=100,
            imported_records=100,
            failed_records=0
        )
        
        self.assertEqual(job.status, 'COMPLETED')
        self.assertEqual(job.imported_records, 100)
    
    def test_import_job_tracking(self):
        """Test tracking import progress"""
        job = GradeImportJob.objects.create(
            created_by=self.user,
            file_name='grades.csv',
            status='PROCESSING',
            total_records=50
        )
        
        # Update progress
        job.imported_records = 25
        job.save()
        
        self.assertEqual(job.imported_records, 25)
    
    def test_import_job_error_handling(self):
        """Test error tracking during import"""
        job = GradeImportJob.objects.create(
            created_by=self.user,
            file_name='grades_error.csv',
            status='PARTIAL',
            total_records=100,
            imported_records=95,
            failed_records=5,
            errors=[
                {'row': 50, 'error': 'Invalid grade value'},
                {'row': 75, 'error': 'Student not found'},
            ]
        )
        
        self.assertEqual(len(job.errors), 2)
        self.assertEqual(job.failed_records, 5)


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
        
        student_profile = StudentProfile.objects.create(
            student=self.user,
            admission_number='STU001'
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
        
        student_profile = StudentProfile.objects.create(
            student=self.user,
            admission_number='STU002'
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
        profile2 = StudentProfile.objects.create(student=student2, admission_number='STU003')
        
        metrics_high = PerformanceMetrics.objects.create(
            student=profile2,
            average_score=35.0,
            risk_level='CRITICAL'
        )
        self.assertEqual(metrics_high.risk_level, 'CRITICAL')


class AnalyticsQueryTestCase(TestCase):
    """Test analytics queries"""
    
    def test_bulk_import_job_queries(self):
        """Test querying multiple import jobs"""
        user = User.objects.create_user(username='admin', password='pass')
        
        for i in range(5):
            GradeImportJob.objects.create(
                created_by=user,
                file_name=f'grades_{i}.csv',
                status='COMPLETED'
            )
        
        jobs = GradeImportJob.objects.filter(status='COMPLETED')
        self.assertEqual(jobs.count(), 5)
