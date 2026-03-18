"""Compliance Tests"""

from django.utils import timezone
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.compliance.models import (
    ComplianceRule,
    RegionalComplianceRequirement,
    ComplianceCheck,
    LegalDocument,
)
from apps.siteconfig.models import RegionConfig

User = get_user_model()


class ComplianceRuleTestCase(TestCase):
    """Test compliance rule creation and management"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def test_create_compliance_rule(self):
        """Test creating a compliance rule"""
        rule = ComplianceRule.objects.create(
            name="GDPR Compliance",
            rule_type="privacy_policy",
            description="GDPR privacy policy requirement",
            applies_globally=True,
            is_mandatory=True,
            created_by=self.user,
        )

        self.assertEqual(rule.name, "GDPR Compliance")
        self.assertEqual(rule.rule_type, "privacy_policy")
        self.assertTrue(rule.is_mandatory)

    def test_compliance_rule_string_representation(self):
        """Test compliance rule string representation"""
        rule = ComplianceRule.objects.create(
            name="Data Retention",
            rule_type="data_retention",
            description="30-day data retention policy",
            created_by=self.user,
        )

        self.assertIn("Data Retention", str(rule))


class ComplianceCheckTestCase(TestCase):
    """Test compliance check functionality"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.region, _ = RegionConfig.objects.get_or_create(
            code="TEST",
            defaults={
                "name": "Test Region",
                "default_language": "en",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.rule = ComplianceRule.objects.create(
            name="Test Rule",
            rule_type="privacy_policy",
            description="Test",
            created_by=self.user,
        )
        self.requirement = RegionalComplianceRequirement.objects.create(
            region=self.region,
            rule=self.rule,
            status="active",
        )

    def test_create_compliance_check(self):
        """Test creating a compliance check"""
        check = ComplianceCheck.objects.create(
            region=self.region,
            requirement=self.requirement,
            check_type="policy_review",
            status="pass",
            findings="All good",
            checked_by=self.user,
        )
        self.assertEqual(check.status, "pass")
        self.assertEqual(check.requirement, self.requirement)


class LegalDocumentTestCase(TestCase):
    """Test legal document management"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def test_create_legal_document(self):
        """Test creating a legal document"""
        region, _ = RegionConfig.objects.get_or_create(
            code="TEST",
            defaults={
                "name": "Test Region",
                "default_language": "en",
                "date_format": "DD/MM/YYYY",
            },
        )
        today = timezone.now().date()
        doc = LegalDocument.objects.create(
            region=region,
            document_type="terms_of_service",
            language="en",
            title="Terms of Service",
            content="Our Terms of Service...",
            version=1,
            effective_date=today,
            created_by=self.user,
        )
        self.assertEqual(doc.title, "Terms of Service")
        self.assertEqual(doc.version, 1)
