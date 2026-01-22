"""Tests for Phase 1.2.9 Compliance Analytics"""
from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from apps.siteconfig.models import RegionConfig
from apps.accounts.models import User
from apps.compliance.models import (
    ComplianceRule, RegionalComplianceRequirement, ComplianceCheck, LegalDocument, ComplianceAuditLog
)
from apps.compliance.analytics import ComplianceAnalytics


class ComplianceAnalyticsTestCase(TestCase):
    """Test compliance analytics engine."""
    
    def setUp(self):
        self.analytics = ComplianceAnalytics()
        self.user = User.objects.create_user(username='admin', email='admin@test.com', password='pass')
        self.region = RegionConfig.objects.create(name='TestRegion', code='TST', default_language='en', timezone='UTC')
    
    def test_compliance_overview_empty(self):
        """Test overview with no compliance data."""
        overview = self.analytics.get_compliance_overview()
        self.assertEqual(overview['total_requirements'], 0)
        self.assertEqual(overview['completion_percentage'], 0)
    
    def test_compliance_overview_with_data(self):
        """Test overview with compliance data."""
        rule = ComplianceRule.objects.create(name='Rule1', rule_type='privacy_policy', description='Test', created_by=self.user)
        RegionalComplianceRequirement.objects.create(region=self.region, rule=rule, status='active', created_by=self.user)
        
        rule2 = ComplianceRule.objects.create(name='Rule2', rule_type='data_retention', description='Test', created_by=self.user)
        RegionalComplianceRequirement.objects.create(region=self.region, rule=rule2, status='pending', created_by=self.user)
        
        overview = self.analytics.get_compliance_overview()
        self.assertEqual(overview['total_requirements'], 2)
        self.assertEqual(overview['completed'], 1)
        self.assertEqual(overview['pending'], 1)
        self.assertEqual(overview['completion_percentage'], 50.0)
    
    def test_regional_metrics(self):
        """Test regional metrics calculation."""
        rule = ComplianceRule.objects.create(name='Rule1', rule_type='privacy_policy', description='Test', created_by=self.user)
        RegionalComplianceRequirement.objects.create(region=self.region, rule=rule, status='active', created_by=self.user)
        
        metrics = self.analytics.get_regional_metrics()
        self.assertIn(self.region.code, metrics)
        self.assertEqual(metrics[self.region.code]['compliance_score'], 100.0)
    
    def test_check_statistics_empty(self):
        """Test check statistics with no checks."""
        stats = self.analytics.get_check_statistics()
        self.assertEqual(stats['total_checks'], 0)
        self.assertEqual(stats['pass_rate'], 0)
    
    def test_check_statistics_with_data(self):
        """Test check statistics with compliance checks."""
        rule = ComplianceRule.objects.create(name='Rule1', rule_type='privacy_policy', description='Test', created_by=self.user)
        req = RegionalComplianceRequirement.objects.create(region=self.region, rule=rule, created_by=self.user)
        
        ComplianceCheck.objects.create(region=self.region, requirement=req, check_type='format_validation', status='pass', findings='OK', checked_by=self.user, issues_found=0)
        ComplianceCheck.objects.create(region=self.region, requirement=req, check_type='format_validation', status='fail', findings='Issues', checked_by=self.user, issues_found=2)
        
        stats = self.analytics.get_check_statistics()
        self.assertEqual(stats['total_checks'], 2)
        self.assertEqual(stats['passed'], 1)
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['pass_rate'], 50.0)
        self.assertEqual(stats['average_issues_per_check'], 1.0)
    
    def test_audit_log_summary(self):
        """Test audit log summary."""
        ComplianceAuditLog.objects.create(region=self.region, action_type='check_performed', description='Test', user=self.user, severity='low')
        ComplianceAuditLog.objects.create(region=self.region, action_type='document_created', description='Test', user=self.user, severity='high')
        
        summary = self.analytics.get_audit_log_summary(days=1)
        self.assertEqual(summary['total_actions'], 2)
        self.assertIn('check_performed', summary['action_breakdown'])
        self.assertIn('low', summary['severity_breakdown'])
    
    def test_document_status(self):
        """Test legal document status."""
        LegalDocument.objects.create(region=self.region, document_type='privacy_policy', language='en', title='Privacy', content='Content', version=1, effective_date=timezone.now().date(), created_by=self.user)
        LegalDocument.objects.create(region=self.region, document_type='privacy_policy', language='fr', title='Confidentialite', content='Contenu', version=1, effective_date=timezone.now().date(), created_by=self.user)
        
        status = self.analytics.get_document_status()
        self.assertEqual(status['total_active_documents'], 2)
    
    def test_timeline_data(self):
        """Test timeline data generation."""
        rule = ComplianceRule.objects.create(name='Rule1', rule_type='privacy_policy', description='Test', created_by=self.user)
        req = RegionalComplianceRequirement.objects.create(region=self.region, rule=rule, created_by=self.user)
        ComplianceCheck.objects.create(region=self.region, requirement=req, check_type='format_validation', status='pass', findings='OK', checked_by=self.user)
        
        timeline = self.analytics.get_timeline_data(days=7)
        self.assertGreater(len(timeline), 0)
        # Verify timeline structure contains required fields
        for day_data in timeline:
            self.assertIn('date', day_data)
            self.assertIn('checks_performed', day_data)
    
    def test_regional_comparison(self):
        """Test regional comparison metrics."""
        region2 = RegionConfig.objects.create(name='TestRegion2', code='TS2', default_language='en', timezone='UTC')
        
        rule = ComplianceRule.objects.create(name='Rule1', rule_type='privacy_policy', description='Test', created_by=self.user)
        RegionalComplianceRequirement.objects.create(region=self.region, rule=rule, status='active', created_by=self.user)
        
        rule2 = ComplianceRule.objects.create(name='Rule2', rule_type='data_retention', description='Test', created_by=self.user)
        RegionalComplianceRequirement.objects.create(region=region2, rule=rule2, status='pending', created_by=self.user)
        
        comparison = self.analytics.get_regional_comparison()
        self.assertEqual(len(comparison), 2)
        self.assertEqual(comparison[0]['region_code'], self.region.code)  # 100% completion first
        self.assertEqual(comparison[0]['requirement_completion'], 100.0)
    
    def test_critical_items_overdue(self):
        """Test critical items detection with overdue requirements."""
        rule = ComplianceRule.objects.create(name='Rule1', rule_type='privacy_policy', description='Test', created_by=self.user)
        past_deadline = timezone.now().date() - timedelta(days=5)
        RegionalComplianceRequirement.objects.create(region=self.region, rule=rule, deadline=past_deadline, created_by=self.user)
        
        critical = self.analytics.get_critical_items()
        self.assertTrue(any(c['type'] == 'overdue_requirement' for c in critical))
        self.assertTrue(any(c['severity'] == 'critical' for c in critical))
    
    def test_critical_items_failed_check(self):
        """Test critical items detection with failed checks."""
        rule = ComplianceRule.objects.create(name='Rule1', rule_type='privacy_policy', description='Test', created_by=self.user)
        req = RegionalComplianceRequirement.objects.create(region=self.region, rule=rule, created_by=self.user)
        ComplianceCheck.objects.create(region=self.region, requirement=req, check_type='format_validation', status='fail', findings='Failed', checked_by=self.user, issues_found=3)
        
        critical = self.analytics.get_critical_items()
        self.assertTrue(any(c['type'] == 'failed_check' for c in critical))
    
    def test_critical_items_expired_doc(self):
        """Test critical items detection with expired documents."""
        past_expiry = timezone.now().date() - timedelta(days=1)
        LegalDocument.objects.create(region=self.region, document_type='privacy_policy', language='en', title='Privacy', content='Content', version=1, effective_date=timezone.now().date(), expiry_date=past_expiry, created_by=self.user)
        
        critical = self.analytics.get_critical_items()
        self.assertTrue(any(c['type'] == 'expired_document' for c in critical))
