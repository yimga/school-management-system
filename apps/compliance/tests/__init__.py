"""Compliance Tests"""

from django.test import TestCase
from django.contrib.auth.models import User
from apps.compliance.models import (
    ComplianceRule, RegionalComplianceRequirement, ComplianceCheck,
    LegalDocument, ComplianceAuditLog, StudentIDFormat, CertificateTemplate
)


class ComplianceRuleTestCase(TestCase):
    """Test compliance rule creation and management"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_compliance_rule(self):
        """Test creating a compliance rule"""
        rule = ComplianceRule.objects.create(
            name='GDPR Compliance',
            rule_type='privacy_policy',
            description='GDPR privacy policy requirement',
            applies_globally=True,
            is_mandatory=True,
            created_by=self.user
        )
        
        self.assertEqual(rule.name, 'GDPR Compliance')
        self.assertEqual(rule.rule_type, 'privacy_policy')
        self.assertTrue(rule.is_mandatory)
    
    def test_compliance_rule_string_representation(self):
        """Test compliance rule string representation"""
        rule = ComplianceRule.objects.create(
            name='Data Retention',
            rule_type='data_retention',
            description='30-day data retention policy',
            created_by=self.user
        )
        
        self.assertIn('Data Retention', str(rule))


class ComplianceCheckTestCase(TestCase):
    """Test compliance check functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.rule = ComplianceRule.objects.create(
            name='Test Rule',
            rule_type='privacy_policy',
            description='Test',
            created_by=self.user
        )
    
    def test_create_compliance_check(self):
        """Test creating a compliance check"""
        check = ComplianceCheck.objects.create(
            rule=self.rule,
            status='passed',
            checked_by=self.user
        )
        
        self.assertEqual(check.status, 'passed')
        self.assertEqual(check.rule, self.rule)


class LegalDocumentTestCase(TestCase):
    """Test legal document management"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_legal_document(self):
        """Test creating a legal document"""
        doc = LegalDocument.objects.create(
            name='Terms of Service',
            document_type='terms_of_service',
            content='Our Terms of Service...',
            version='1.0',
            created_by=self.user
        )
        
        self.assertEqual(doc.name, 'Terms of Service')
        self.assertEqual(doc.version, '1.0')
