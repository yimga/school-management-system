from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date, timedelta
from django.utils import timezone
from apps.siteconfig.models import RegionConfig
from apps.compliance.models import (
    ComplianceRule, RegionalComplianceRequirement, ComplianceCheck,
    LegalDocument, ComplianceAuditLog, StudentIDFormat, CertificateTemplate
)
from apps.compliance.validators import RegionalComplianceValidator

User = get_user_model()

class ComplianceRuleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', email='admin@test.com', password='pass')
    
    def test_create_compliance_rule(self):
        rule = ComplianceRule.objects.create(
            name='Data Retention',
            rule_type='data_retention',
            description='7 year retention',
            created_by=self.user
        )
        self.assertEqual(rule.name, 'Data Retention')
    
    def test_rule_str(self):
        rule = ComplianceRule.objects.create(
            name='Privacy Policy',
            rule_type='privacy_policy',
            description='Test',
            created_by=self.user
        )
        self.assertIn('Privacy Policy', str(rule))

class RegionalComplianceRequirementTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', email='admin@test.com', password='pass')
        self.region = RegionConfig.objects.create(
            name='Cameroon', code='CMR', timezone='Africa/Douala'
        )
        self.rule = ComplianceRule.objects.create(
            name='Rule1', rule_type='data_retention', description='Test', created_by=self.user
        )
    
    def test_create_requirement(self):
        req = RegionalComplianceRequirement.objects.create(
            region=self.region, rule=self.rule, status='pending', created_by=self.user
        )
        self.assertEqual(req.region.code, 'CMR')
    
    def test_is_overdue(self):
        past = timezone.now().date() - timedelta(days=10)
        req = RegionalComplianceRequirement.objects.create(
            region=self.region, rule=self.rule, deadline=past, created_by=self.user
        )
        self.assertTrue(req.is_overdue())
    
    def test_not_overdue(self):
        future = timezone.now().date() + timedelta(days=30)
        req = RegionalComplianceRequirement.objects.create(
            region=self.region, rule=self.rule, deadline=future, created_by=self.user
        )
        self.assertFalse(req.is_overdue())

class ComplianceCheckTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='checker', email='checker@test.com', password='pass')
        self.region = RegionConfig.objects.create(
            name='Kenya', code='KEN', timezone='Africa/Nairobi'
        )
        self.rule = ComplianceRule.objects.create(
            name='Rule2', rule_type='certificate_format', description='Test', created_by=self.user
        )
        self.req = RegionalComplianceRequirement.objects.create(
            region=self.region, rule=self.rule, created_by=self.user
        )
    
    def test_create_check(self):
        check = ComplianceCheck.objects.create(
            region=self.region, requirement=self.req, check_type='format_validation',
            status='pass', findings='OK', issues_found=0, checked_by=self.user
        )
        self.assertEqual(check.status, 'pass')
    
    def test_check_with_issues(self):
        check = ComplianceCheck.objects.create(
            region=self.region, requirement=self.req, check_type='data_validation',
            status='fail', findings='Data issues', issues_found=3, checked_by=self.user
        )
        self.assertEqual(check.issues_found, 3)

class LegalDocumentTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', email='admin@test.com', password='pass')
        self.region = RegionConfig.objects.create(
            name='Nigeria', code='NGA', timezone='Africa/Lagos'
        )
    
    def test_create_document(self):
        doc = LegalDocument.objects.create(
            region=self.region, document_type='privacy_policy', language='en',
            title='Privacy', content='<p>Content</p>', version=1,
            effective_date=timezone.now().date(), created_by=self.user
        )
        self.assertEqual(doc.language, 'en')
    
    def test_multi_language_documents(self):
        for lang in ['en', 'fr', 'sw']:
            LegalDocument.objects.create(
                region=self.region, document_type='terms_of_service', language=lang,
                title=f'Terms {lang}', content='Content', version=1,
                effective_date=timezone.now().date(), created_by=self.user
            )
        
        docs = LegalDocument.objects.filter(region=self.region, document_type='terms_of_service')
        self.assertEqual(docs.count(), 3)
    
    def test_is_expired(self):
        past = timezone.now().date() - timedelta(days=1)
        doc = LegalDocument.objects.create(
            region=self.region, document_type='data_agreement', language='en',
            title='Data', content='Content', version=1,
            effective_date=timezone.now().date(), expiry_date=past, created_by=self.user
        )
        self.assertTrue(doc.is_expired())

class ComplianceAuditLogTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='auditor', email='auditor@test.com', password='pass')
        self.region = RegionConfig.objects.create(
            name='USA', code='USA', timezone='America/New_York'
        )
    
    def test_create_audit_log(self):
        log = ComplianceAuditLog.objects.create(
            region=self.region, action_type='check_performed',
            description='Test', user=self.user, severity='medium'
        )
        self.assertEqual(log.action_type, 'check_performed')

class StudentIDFormatTestCase(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='France', code='FRA', timezone='Europe/Paris'
        )
    
    def test_create_format(self):
        fmt = StudentIDFormat.objects.create(
            region=self.region, format_pattern='FRA-YY-nnnn', prefix='FRA',
            min_length=10, max_length=20, example_id='FRA-26-0001'
        )
        self.assertEqual(fmt.prefix, 'FRA')

class CertificateTemplateTestCase(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='UK', code='GBR', timezone='Europe/London'
        )
    
    def test_create_template(self):
        tpl = CertificateTemplate.objects.create(
            region=self.region, name='GCSE', description='Standard',
            paper_size='A4', orientation='landscape', requires_school_seal=True,
            template_html='<h1>Cert</h1>', version=1, is_active=True
        )
        self.assertEqual(tpl.paper_size, 'A4')
    
    def test_template_requirements(self):
        tpl = CertificateTemplate.objects.create(
            region=self.region, name='Diploma', requires_principal_signature=True,
            requires_official_stamp=True, template_html='<h1>Diploma</h1>',
            version=1
        )
        self.assertTrue(tpl.requires_principal_signature)
        self.assertTrue(tpl.requires_official_stamp)

class RegionalComplianceValidatorTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', email='admin@test.com', password='pass')
        self.region = RegionConfig.objects.create(
            name='Nigeria', code='NGA', timezone='Africa/Lagos'
        )
    
    def test_compliance_score(self):
        rule = ComplianceRule.objects.create(
            name='TestRule', rule_type='data_retention', description='Test', created_by=self.user
        )
        
        for i in range(5):
            status = 'active' if i < 3 else 'pending'
            RegionalComplianceRequirement.objects.create(
                region=self.region,
                rule=ComplianceRule.objects.create(
                    name=f'Rule{i}', rule_type='data_retention', description='Test', created_by=self.user
                ),
                status=status, created_by=self.user
            )
        
        reqs = RegionalComplianceRequirement.objects.filter(region=self.region)
        validator = RegionalComplianceValidator(self.region)
        score = validator.generate_compliance_score(reqs)
        self.assertEqual(score, 60.0)
    
    def test_empty_score(self):
        validator = RegionalComplianceValidator(self.region)
        score = validator.generate_compliance_score([])
        self.assertEqual(score, 0)
