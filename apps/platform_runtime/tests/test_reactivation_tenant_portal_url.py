"""Reactivation emails must not route tenants to the manager console."""

from django.test import TestCase, override_settings

from apps.platform_runtime.reactivation_engine import _portal_url_for_reactivation
from apps.schools.models import School


@override_settings(RMC_PUBLIC_SITE_URL="https://runmycampus.com")
class ReactivationPortalUrlTests(TestCase):
    def test_inactive_school_uses_public_login(self):
        school = School.objects.create(
            name="St Jude",
            slug="st-jude",
            subdomain="st-jude",
            is_active=False,
        )
        self.assertEqual(
            _portal_url_for_reactivation(school),
            "https://runmycampus.com/authentication/login/",
        )

    def test_active_school_uses_tenant_subdomain(self):
        school = School.objects.create(
            name="St Jude Live",
            slug="st-jude-live",
            subdomain="st-jude-live",
            is_active=True,
        )
        url = _portal_url_for_reactivation(school)
        self.assertIn("st-jude-live.runmycampus.com", url)
        self.assertNotIn("manager.runmycampus.com", url)
