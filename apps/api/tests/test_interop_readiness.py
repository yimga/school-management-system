import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.interop.district_readiness import parse_district_readiness_dict
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

    def test_district_readiness_sample_fixtures_parse_from_api_test_tree(self):
        """Interop readiness tests stay aligned with repo ``fixtures/interop`` samples (§11.4 depth)."""
        root = Path(settings.BASE_DIR)
        for rel in (
            "fixtures/interop/edfi_district_readiness_sample.json",
            "fixtures/interop/ceds_district_readiness_sample.json",
        ):
            path = root / rel
            self.assertTrue(path.is_file(), msg=f"missing {rel}")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)
            self.assertGreaterEqual(len(data), 2)
            out = parse_district_readiness_dict(data)
            self.assertIn("source_system", out)
            self.assertIn("district_identifier", out)
            self.assertIn("name", out)

    def test_district_readiness_sample_endpoint_returns_parsed_fixture_shape(self):
        """HTTP stub returns the same canonical dict as ``parse_district_readiness_dict`` (batch 14 #139)."""
        url = reverse("api:interop-district-readiness-sample")
        r = self.client.get(f"{url}?school_slug={self.school.slug}&fixture=edfi")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        path = Path(settings.BASE_DIR) / "fixtures/interop/edfi_district_readiness_sample.json"
        expected = parse_district_readiness_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(body, expected)

    def test_district_readiness_sample_invalid_fixture_returns_400(self):
        url = reverse("api:interop-district-readiness-sample")
        r = self.client.get(
            f"{url}?school_slug={self.school.slug}&fixture=not-a-fixture"
        )
        self.assertEqual(r.status_code, 400)

    def test_edfi_readiness_echoes_district_readiness_from_integration_config(self):
        """Fixture-shaped ``parse_district_readiness_dict`` output surfaces on Ed-Fi stub (batch 14 #139)."""
        path = (
            Path(settings.BASE_DIR) / "fixtures/interop/edfi_district_readiness_sample.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        canon = parse_district_readiness_dict(data)
        ServiceIntegration.objects.create(
            school=self.school,
            service_name="Ed-Fi fixture district",
            service_type=ServiceIntegration.ServiceType.OTHER,
            endpoint_url="https://api.example.com/edfi",
            config={"district_readiness": canon, "bearer_token": "fixture-token"},
            is_active=True,
        )
        response = self.client.get(self._url("api:interop-edfi"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload.get("district_readiness") or {}
        self.assertEqual(
            block.get("district_identifier"), "rmc-fixture-district-001"
        )
        self.assertEqual(block.get("source_system"), "edfi")
        self.assertIn("RunMyCampus fixture district", block.get("name", ""))

    def test_ceds_readiness_echoes_district_readiness_from_integration_config(self):
        """CEDS stub echoes CEDS-shaped ``district_readiness`` (batch 15 #149)."""
        path = (
            Path(settings.BASE_DIR)
            / "fixtures/interop/ceds_district_readiness_sample.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        canon = parse_district_readiness_dict(data)
        ServiceIntegration.objects.create(
            school=self.school,
            service_name="CEDS fixture LEA",
            service_type=ServiceIntegration.ServiceType.OTHER,
            endpoint_url="https://api.example.com/ceds",
            config={"district_readiness": canon, "bearer_token": "fixture-token"},
            is_active=True,
        )
        response = self.client.get(self._url("api:interop-ceds"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload.get("district_readiness") or {}
        self.assertEqual(block.get("district_identifier"), "rmc-fixture-lea-001")
        self.assertEqual(block.get("source_system"), "ceds")
        self.assertIn("fixture LEA", block.get("name", ""))
