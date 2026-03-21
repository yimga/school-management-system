"""
World Engine: switch_to_tenant requires JIT consent when JIT_IMPERSONATION_REQUIRE_CONSENT is True.
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School
from apps.siteconfig.models import RegionConfig

User = get_user_model()


class SwitchToTenantConsentTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.first()
        if not self.region:
            self.region = RegionConfig.objects.create(
                code="CM",
                name="Cameroon",
                default_language="en",
                timezone="Africa/Douala",
            )
        self.school = School.objects.create(
            name="Consent Test School",
            slug="consent-test-school",
            subdomain="consent-test-school",
            is_active=True,
            default_region=self.region,
        )
        self.superuser = User.objects.create_user(
            username="super_test",
            email="super@test.com",
            password="testpass123",
            is_superuser=True,
            is_staff=True,
        )

    @override_settings(JIT_IMPERSONATION_REQUIRE_CONSENT=True)
    def test_switch_redirects_when_consent_missing(self):
        """When consent is not granted, switch_to_tenant redirects to super dashboard with error."""
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("super:switch_to_tenant"),
            data={
                "school_id": str(self.school.id),
                "impersonation_reason": "Testing consent gate — operator justification.",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("super", response.url or "")
        self.school.refresh_from_db()
        self.assertIsNone(self.school.impersonation_consent_granted_at)

    @override_settings(JIT_IMPERSONATION_REQUIRE_CONSENT=True)
    def test_switch_succeeds_when_consent_granted(self):
        """When consent is granted, switch_to_tenant redirects to tenant impersonation URL."""
        self.school.impersonation_consent_granted_at = timezone.now()
        self.school.impersonation_consent_granted_by_id = self.superuser.id
        self.school.save(
            update_fields=[
                "impersonation_consent_granted_at",
                "impersonation_consent_granted_by_id",
            ]
        )
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("super:switch_to_tenant"),
            data={
                "school_id": str(self.school.id),
                "impersonation_reason": "Testing consent granted — operator justification.",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("impersonate=", response.url or "")
