"""Wedge 45: FederationSsoHealth updated on SAML/OIDC outcomes."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.federation_sso_health import record_sso_failure, record_sso_success
from apps.accounts.models import FederationSsoHealth
from apps.schools.models import School
from apps.siteconfig.models import ServiceIntegration


class FederationSsoHealthHelpersTests(TestCase):
    def test_success_increments(self):
        school = School.objects.create(
            name="H1", slug="fed-h1", subdomain="fedh1", is_active=True
        )
        si = ServiceIntegration.objects.create(
            school=school,
            service_name="Test IdP",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
            config={"token_endpoint": "https://idp.example/token"},
        )
        record_sso_success(si.pk)
        record_sso_success(si.pk)
        h = FederationSsoHealth.objects.get(service_integration=si)
        self.assertEqual(h.success_count, 2)
        self.assertIsNotNone(h.last_success_at)

    def test_failure_tracks(self):
        school = School.objects.create(
            name="H2", slug="fed-h2", subdomain="fedh2", is_active=True
        )
        si = ServiceIntegration.objects.create(
            school=school,
            service_name="Test IdP2",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
            config={},
        )
        record_sso_failure(si.pk, "Invalid nonce")
        h = FederationSsoHealth.objects.get(service_integration=si)
        self.assertEqual(h.failure_count, 1)
        self.assertIn("nonce", h.last_error_summary)


class OidcCallbackHealthTests(TestCase):
    def test_oidc_failure_updates_health(self):
        school = School.objects.create(
            name="H3", slug="fed-h3", subdomain="fedh3", is_active=True
        )
        si = ServiceIntegration.objects.create(
            school=school,
            service_name="OIDC Test",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
            config={"token_endpoint": "https://x/token"},
        )
        url = reverse("accounts:oidc_callback", args=[si.pk])
        resp = self.client.get(url, {"state": "no-session-pending"})
        self.assertEqual(resp.status_code, 403)
        h = FederationSsoHealth.objects.get(service_integration=si)
        self.assertGreaterEqual(h.failure_count, 1)
