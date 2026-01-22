"""Phase 8 Task 1: Compliance Tests"""

from django.test import TestCase, Client
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta
from apps.compliance.models import (
    AccessLog, AuditLog, ThreatDetectionConfig, IncidentTicket,
    IPAccessRule, CountryAccessRule
)
from apps.compliance.access_control import (
    AccessControlManager, RoleBasedAccessControl, ResourceLevelSecurity
)
from apps.compliance.threat_detection import ThreatDetector


class AccessControlTestCase(TestCase):
    """Test access control system"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.admin = User.objects.create_superuser(
            username='admin',
            password='admin123'
        )
    
    def test_ip_access_allow(self):
        """Test IP access allow rule"""
        rule = IPAccessRule.objects.create(
            ip_address='192.168.1.1',
            action='ALLOW'
        )
        self.assertTrue(AccessControlManager.check_ip_access('192.168.1.1'))
    
    def test_ip_access_deny(self):
        """Test IP access deny rule"""
        rule = IPAccessRule.objects.create(
            ip_address='192.168.1.2',
            action='DENY'
        )
        self.assertFalse(AccessControlManager.check_ip_access('192.168.1.2'))
    
    def test_country_access_deny(self):
        """Test country access deny"""
        rule = CountryAccessRule.objects.create(
            country_code='XX',
            country_name='Test Country',
            action='DENY'
        )
        self.assertFalse(AccessControlManager.check_country_access('XX'))
    
    def test_create_roles(self):
        """Test RBAC role creation"""
        RoleBasedAccessControl.create_roles()
        
        roles = Group.objects.filter(name__in=['ADMIN', 'TEACHER', 'PARENT'])
        self.assertEqual(roles.count(), 3)
    
    def test_assign_role(self):
        """Test role assignment"""
        Group.objects.create(name='TEACHER')
        
        RoleBasedAccessControl.assign_role(self.user, 'TEACHER')
        
        self.assertTrue(self.user.groups.filter(name='TEACHER').exists())


class AuditLoggingTestCase(TestCase):
    """Test audit logging"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_audit_log(self):
        """Test creating audit log entry"""
        log = AuditLog.objects.create(
            user=self.user,
            action='CREATE',
            app_label='evals',
            model_name='Eval',
            object_id=1,
            object_repr='Test Eval',
            ip_address='127.0.0.1'
        )
        
        self.assertEqual(log.action, 'CREATE')
        self.assertEqual(log.model_name, 'Eval')
    
    def test_audit_log_query(self):
        """Test querying audit logs"""
        for i in range(5):
            AuditLog.objects.create(
                user=self.user,
                action='UPDATE',
                app_label='evals',
                model_name='Grade',
                object_id=i,
                object_repr=f'Grade {i}',
                ip_address='127.0.0.1'
            )
        
        logs = AuditLog.objects.filter(action='UPDATE')
        self.assertEqual(logs.count(), 5)


class AccessLogTestCase(TestCase):
    """Test access logging"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
    
    def test_create_access_log(self):
        """Test creating access log"""
        log = AccessLog.objects.create(
            user=self.user,
            access_type='LOGIN',
            resource='/api/auth/login/',
            ip_address='127.0.0.1',
            status='SUCCESS'
        )
        
        self.assertEqual(log.access_type, 'LOGIN')
        self.assertEqual(log.status, 'SUCCESS')
    
    def test_failed_login_logging(self):
        """Test logging failed login attempts"""
        for i in range(3):
            AccessLog.objects.create(
                access_type='FAILED_LOGIN',
                resource='/api/auth/login/',
                ip_address='192.168.1.1',
                status='FAILURE'
            )
        
        failed = AccessLog.objects.filter(
            ip_address='192.168.1.1',
            status='FAILURE'
        )
        self.assertEqual(failed.count(), 3)


class ThreatDetectionTestCase(TestCase):
    """Test threat detection"""
    
    def setUp(self):
        self.config = ThreatDetectionConfig.objects.create(
            threat_type='BRUTE_FORCE',
            threshold=5,
            time_window=3600,
            action='ALERT'
        )
    
    def test_brute_force_detection(self):
        """Test brute force detection"""
        # Create multiple failed logins
        for i in range(6):
            AccessLog.objects.create(
                access_type='FAILED_LOGIN',
                resource='/login/',
                ip_address='192.168.1.100',
                status='FAILURE',
                timestamp=timezone.now()
            )
        
        ThreatDetector.check_brute_force()
        
        # Check if incident was created
        incident = IncidentTicket.objects.filter(
            title='BRUTE_FORCE'
        ).first()
        
        self.assertIsNotNone(incident)
    
    def test_rate_limit_violation(self):
        """Test rate limit detection"""
        config = ThreatDetectionConfig.objects.create(
            threat_type='RATE_LIMIT_VIOLATION',
            threshold=50,
            time_window=60,
            action='ALERT'
        )
        
        # Create 51 access logs from same IP
        for i in range(51):
            AccessLog.objects.create(
                access_type='API_CALL',
                resource='/api/grades/',
                ip_address='192.168.1.200',
                status='SUCCESS',
                timestamp=timezone.now()
            )
        
        ThreatDetector.check_rate_limit_violation()
        
        incident = IncidentTicket.objects.filter(
            title='RATE_LIMIT_VIOLATION'
        ).first()
        
        self.assertIsNotNone(incident)


class IncidentTicketTestCase(TestCase):
    """Test incident ticket system"""
    
    def test_create_incident(self):
        """Test creating incident ticket"""
        incident = IncidentTicket.objects.create(
            incident_id='INC-20260122-001',
            title='Brute Force Attack',
            description='Multiple failed login attempts',
            severity='CRITICAL',
            status='OPEN'
        )
        
        self.assertEqual(incident.status, 'OPEN')
        self.assertEqual(incident.severity, 'CRITICAL')
    
    def test_incident_resolution(self):
        """Test incident resolution workflow"""
        incident = IncidentTicket.objects.create(
            incident_id='INC-20260122-002',
            title='Suspicious Activity',
            description='Unusual access pattern detected',
            severity='HIGH',
            status='INVESTIGATING'
        )
        
        incident.status = 'RESOLVED'
        incident.resolved_at = timezone.now()
        incident.notes = 'False positive - routine maintenance'
        incident.save()
        
        self.assertEqual(incident.status, 'RESOLVED')
        self.assertIsNotNone(incident.resolved_at)


class ComplianceReportTestCase(TestCase):
    """Test compliance reporting"""
    
    def test_generate_audit_report(self):
        """Test generating audit report"""
        from apps.compliance.models import ComplianceReport
        
        report = ComplianceReport.objects.create(
            report_type='AUDIT_TRAIL',
            period_start=timezone.now().date() - timedelta(days=30),
            period_end=timezone.now().date(),
            summary='30-day audit trail report',
            findings={
                'total_changes': 150,
                'changes_by_user': {}
            }
        )
        
        self.assertEqual(report.report_type, 'AUDIT_TRAIL')
        self.assertIsNotNone(report.findings)
