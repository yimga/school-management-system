"""Comprehensive tests for Phase 1.2.8: Compliance & Legal Framework"""
from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from apps.siteconfig.models import RegionConfig
from apps.accounts.models import User
from apps.compliance.models import (
    ComplianceRule, RegionalComplianceRequirement, ComplianceCheck, LegalDocument, ComplianceAuditLog, StudentIDFormat, CertificateTemplate
)
from apps.compliance.validators import StudentIDValidator, CertificateValidator, RegionalComplianceValidator

class ComplianceRuleTestCase(TestCase):
    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(username='compliance_rule_%s' % uid, email='rule_%s@test.com' % uid, password='pass')
    
    def test_create_rule(self):
        rule = ComplianceRule.objects.create(name='Data Retention', rule_type='data_retention', description='Test', created_by=self.user)
        self.assertEqual(rule.name, 'Data Retention')
    
    def test_rule_string_representation(self):
        rule = ComplianceRule.objects.create(name='Cert Format', rule_type='certificate_format', description='Test', created_by=self.user)
        self.assertIn('Cert Format', str(rule))

class RegionalComplianceRequirementTestCase(TestCase):
    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(username='compliance_req_%s' % uid, email='req_%s@test.com' % uid, password='pass')
        self.region, _ = RegionConfig.objects.get_or_create(code='TMR', defaults={'name': 'TestCMR', 'default_language': 'en', 'timezone': 'Africa/Douala', 'date_format': 'DD/MM/YYYY'})
        self.rule = ComplianceRule.objects.create(name='Data Protection', rule_type='privacy_policy', description='Test', created_by=self.user)
    
    def test_create_requirement(self):
        req = RegionalComplianceRequirement.objects.create(region=self.region, rule=self.rule, status='pending', created_by=self.user)
        self.assertEqual(req.region.code, 'TMR')
    
    def test_is_overdue(self):
        past_deadline = timezone.now().date() - timedelta(days=10)
        req = RegionalComplianceRequirement.objects.create(region=self.region, rule=self.rule, deadline=past_deadline, created_by=self.user)
        self.assertTrue(req.is_overdue())

class ComplianceCheckTestCase(TestCase):
    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(username='compliance_checker_%s' % uid, email='checker_%s@test.com' % uid, password='pass')
        self.admin = User.objects.create_user(username='compliance_admin_%s' % uid, email='admin_%s@test.com' % uid, password='pass')
        self.region, _ = RegionConfig.objects.get_or_create(code='TKN', defaults={'name': 'TestKEN', 'default_language': 'en', 'timezone': 'Africa/Nairobi', 'date_format': 'DD/MM/YYYY'})
        self.rule = ComplianceRule.objects.create(name='Document Validation', rule_type='document_validation', description='Test', created_by=self.admin)
        self.requirement = RegionalComplianceRequirement.objects.create(region=self.region, rule=self.rule, status='active', created_by=self.admin)
    
    def test_create_compliance_check(self):
        check = ComplianceCheck.objects.create(region=self.region, requirement=self.requirement, check_type='format_validation', status='pass', findings='OK', checked_by=self.user)
        self.assertEqual(check.status, 'pass')

class LegalDocumentTestCase(TestCase):
    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(username='compliance_legal_%s' % uid, email='legal_%s@test.com' % uid, password='pass')
        self.region, _ = RegionConfig.objects.get_or_create(code='TNG', defaults={'name': 'TestNGA', 'default_language': 'en', 'timezone': 'Africa/Lagos', 'date_format': 'DD/MM/YYYY'})
    
    def test_create_document(self):
        doc = LegalDocument.objects.create(region=self.region, document_type='privacy_policy', language='en', title='Privacy', content='<h1>Policy</h1>', version=1, effective_date=timezone.now().date(), created_by=self.user)
        self.assertEqual(doc.document_type, 'privacy_policy')
    
    def test_multi_language_documents(self):
        for lang in ['en', 'fr', 'sw', 'yo', 'pid', 'ha']:
            LegalDocument.objects.create(region=self.region, document_type='privacy_policy', language=lang, title=f'Policy ({lang})', content='Content', version=1, effective_date=timezone.now().date(), created_by=self.user)
        docs = LegalDocument.objects.filter(region=self.region, document_type='privacy_policy')
        self.assertEqual(docs.count(), 6)

class StudentIDValidatorTestCase(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(code='TC2', defaults={'name': 'TestCMR2', 'default_language': 'en', 'timezone': 'Africa/Douala', 'date_format': 'DD/MM/YYYY'})
        self.validator = StudentIDValidator(self.region)
    
    def test_valid_student_id(self):
        id_format = StudentIDFormat.objects.create(region=self.region, format_pattern='CMR-YY-nnnn', prefix='CMR', min_length=10, max_length=20, example_id='CMR-24-0001')
        result = self.validator.validate('CMR-24-0001', id_format)
        self.assertTrue(result)

class CertificateValidatorTestCase(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(code='TK2', defaults={'name': 'TestKEN2', 'default_language': 'en', 'timezone': 'Africa/Nairobi', 'date_format': 'DD/MM/YYYY'})
        self.validator = CertificateValidator(self.region)
    
    def test_valid_certificate(self):
        cert_data = {'student_name': 'John', 'course': 'KCSE', 'date_issued': date.today().isoformat(), 'achievement_level': 'A'}
        result = self.validator.validate(cert_data)
        self.assertTrue(result)

class ComplianceAuditLogTestCase(TestCase):
    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(username='compliance_auditor_%s' % uid, email='auditor_%s@test.com' % uid, password='pass')
        self.region, _ = RegionConfig.objects.get_or_create(code='TUS', defaults={'name': 'TestUSA', 'default_language': 'en', 'timezone': 'America/New_York', 'date_format': 'DD/MM/YYYY'})
    
    def test_audit_log_creation(self):
        log = ComplianceAuditLog.objects.create(region=self.region, action_type='check_performed', description='Check done', user=self.user, severity='medium')
        self.assertEqual(log.action_type, 'check_performed')

class RegionalComplianceValidatorTestCase(TestCase):
    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(username='compliance_validator_%s' % uid, email='validator_%s@test.com' % uid, password='pass')
        self.region, _ = RegionConfig.objects.get_or_create(code='TN2', defaults={'name': 'TestNGA2', 'default_language': 'en', 'timezone': 'Africa/Lagos', 'date_format': 'DD/MM/YYYY'})
        self.validator = RegionalComplianceValidator(self.region)
    
    def test_compliance_score(self):
        for i in range(5):
            status = 'active' if i < 3 else 'pending'
            r = ComplianceRule.objects.create(name=f'Rule{i}', rule_type='privacy_policy', description='Test', created_by=self.user)
            RegionalComplianceRequirement.objects.create(region=self.region, rule=r, status=status, created_by=self.user)
        
        requirements = RegionalComplianceRequirement.objects.filter(region=self.region)
        score = self.validator.generate_compliance_score(requirements)
        self.assertEqual(score, 60.0)


class ComplianceDashboardRBACTestCase(TestCase):
    """Dashboard access: only staff/ADMIN/LEADERSHIP can access main compliance dashboard."""

    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent_rbac", email="parent_rbac@test.com", password="pass"
        )
        self.parent.role = User.Role.PARENT
        self.parent.save(update_fields=["role"])
        self.admin = User.objects.create_user(
            username="admin_rbac", email="admin_rbac@test.com", password="pass"
        )
        self.admin.role = User.Role.ADMIN
        self.admin.save(update_fields=["role"])

    def test_non_staff_gets_redirected_from_dashboard(self):
        self.client.force_login(self.parent)
        response = self.client.get("/compliance/dashboard/")
        # user_passes_test fails -> redirect to login (or 403 if configured)
        self.assertIn(response.status_code, (302, 403))
