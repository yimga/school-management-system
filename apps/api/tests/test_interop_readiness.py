from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.schools.models import School
from apps.siteconfig.models import ServiceIntegration


class InteropReadinessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Interop School",
            slug="interop-school",
            subdomain="interop-school",
            is_active=True,
        )

    def _url(self, name: str) -> str:
        return f"{reverse(name)}?school_slug={self.school.slug}"

    def test_oneroster_reports_ready_when_auth_config_present(self):
        ServiceIntegration.objects.create(
            school=self.school,
            service_name="OneRoster District Sync",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            endpoint_url="https://district.example.com/oneroster",
            config={"bearer_token": "secret-token"},
            is_active=True,
        )

        response = self.client.get(self._url("api:interop-oneroster"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("implemented"))
        self.assertEqual(payload.get("status"), "ready")
        self.assertIn("manifest", payload.get("endpoints", {}))

    def test_oneroster_reports_needs_configuration_without_auth(self):
        ServiceIntegration.objects.create(
            school=self.school,
            service_name="OneRoster District Sync",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            endpoint_url="https://district.example.com/oneroster",
            config={},
            is_active=True,
        )

        response = self.client.get(self._url("api:interop-oneroster"))
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload.get("status"), "needs_configuration")

    def test_lti13_reports_ready_with_required_fields(self):
        integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="LTI 1.3 District Tool",
            service_type=ServiceIntegration.ServiceType.LTI,
            endpoint_url="https://idp.example.com/authorize",
            client_id="lti-client",
            config={
                "authorization_endpoint": "https://idp.example.com/authorize",
                "deployment_id": "deploy-001",
            },
            is_active=True,
        )

        response = self.client.get(self._url("api:interop-lti13"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "ready")
        endpoints = payload.get("endpoints", {})
        self.assertIn(str(integration.pk), endpoints.get("oidc_login", ""))
        self.assertIn("jwks", endpoints)

    def test_oneroster_discovery_returns_429_when_rate_limited(self):
        with patch(
            "apps.api.interop_stubs.throttle_ip_request", return_value=(False, 900)
        ):
            response = self.client.get(self._url("api:interop-oneroster"))
        self.assertEqual(response.status_code, 429)
        payload = response.json()
        self.assertEqual(payload.get("status"), "rate_limited")
        self.assertEqual(payload.get("service"), "oneroster")

    def test_lti13_discovery_returns_429_when_rate_limited(self):
        with patch(
            "apps.api.interop_stubs.throttle_ip_request", return_value=(False, 900)
        ):
            response = self.client.get(self._url("api:interop-lti13"))
        self.assertEqual(response.status_code, 429)
        payload = response.json()
        self.assertEqual(payload.get("status"), "rate_limited")
        self.assertEqual(payload.get("service"), "lti13")
