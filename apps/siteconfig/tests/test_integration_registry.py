from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.integration_registry import (
    backfill_service_integrations_from_legacy,
    resolve_active_integration,
    resolve_service_integration,
)
from apps.siteconfig.models import Integration, ServiceIntegration


class IntegrationRegistryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Registry School",
            slug="registry-school",
            subdomain="registry-school",
            is_active=True,
        )

    def test_resolve_prefers_service_integration_over_legacy(self):
        Integration.objects.create(
            school=self.school,
            name="Moodle Legacy",
            slug="moodle",
            provider="other",
            category="LMS",
            enabled=True,
            config={"endpoint_url": "https://legacy.example.org/lti"},
        )
        service = ServiceIntegration.objects.create(
            school=self.school,
            service_name="moodle",
            service_type=ServiceIntegration.ServiceType.LTI,
            endpoint_url="https://new.example.org/lti",
            enabled_scopes=["grades.read"],
            config={"deployment_id": "dep-1"},
            is_active=True,
        )

        resolved = resolve_active_integration(self.school, "moodle")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.source, "service_integration")
        self.assertEqual(resolved.integration_id, service.pk)
        self.assertEqual(resolved.endpoint_url, "https://new.example.org/lti")

    def test_resolve_falls_back_to_legacy(self):
        legacy = Integration.objects.create(
            school=self.school,
            name="Payments Legacy",
            slug="payments-core",
            provider="payments",
            category="PAYMENT",
            enabled=True,
            config={
                "endpoint_url": "https://legacy-payments.example.org",
                "enabled_scopes": ["charge"],
            },
        )

        resolved = resolve_active_integration(self.school, "payments-core")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.source, "legacy_integration")
        self.assertEqual(resolved.integration_id, legacy.pk)
        self.assertEqual(resolved.service_type, ServiceIntegration.ServiceType.OAUTH)
        self.assertEqual(resolved.enabled_scopes, ["charge"])

    def test_backfill_creates_service_integrations_from_legacy(self):
        Integration.objects.create(
            school=self.school,
            name="SMS Legacy",
            slug="sms-gateway",
            provider="sms",
            category="OTHER",
            enabled=True,
            config={"endpoint_url": "https://sms.example.org"},
        )

        preview = backfill_service_integrations_from_legacy(
            school=self.school, dry_run=True
        )
        self.assertEqual(len(preview), 1)
        self.assertEqual(preview[0]["action"], "would_upsert")
        self.assertEqual(ServiceIntegration.objects.count(), 0)

        result = backfill_service_integrations_from_legacy(
            school=self.school, dry_run=False
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["action"], "created")
        service = ServiceIntegration.objects.get(
            school=self.school, service_name="sms-gateway"
        )
        self.assertEqual(service.service_type, ServiceIntegration.ServiceType.WEBHOOK)
        self.assertEqual(service.endpoint_url, "https://sms.example.org")
        self.assertEqual(service.config.get("_legacy_provider"), "sms")

    def test_backfill_updates_existing_service_integration(self):
        Integration.objects.create(
            school=self.school,
            name="Analytics Legacy",
            slug="analytics-core",
            provider="analytics",
            category="OTHER",
            enabled=True,
            config={"endpoint_url": "https://legacy-analytics.example.org"},
        )
        service = ServiceIntegration.objects.create(
            school=self.school,
            service_name="analytics-core",
            service_type=ServiceIntegration.ServiceType.OTHER,
            endpoint_url="https://old.example.org",
            enabled_scopes=[],
            config={},
            is_active=True,
        )

        result = backfill_service_integrations_from_legacy(
            school=self.school, dry_run=False
        )
        self.assertEqual(result[0]["action"], "updated")

        service.refresh_from_db()
        self.assertEqual(service.service_type, ServiceIntegration.ServiceType.OAUTH)
        self.assertEqual(service.endpoint_url, "https://legacy-analytics.example.org")
        self.assertEqual(
            service.config.get("_legacy_integration_id"), result[0]["legacy_id"]
        )

    def test_resolve_service_integration_autobackfills_from_legacy(self):
        Integration.objects.create(
            school=self.school,
            name="District SCIM Legacy",
            slug="district-scim",
            provider="analytics",
            category="OTHER",
            enabled=True,
            config={
                "service_hint": "scim",
                "endpoint_url": "https://legacy-idp.example.org/scim",
                "bearer_token": "legacy-token",
            },
        )

        resolved = resolve_service_integration(
            self.school,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            service_name="scim",
            name_hints=["scim"],
            allow_legacy_backfill=True,
        )
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.service_type, ServiceIntegration.ServiceType.OAUTH)
        self.assertEqual(resolved.endpoint_url, "https://legacy-idp.example.org/scim")
        self.assertEqual(resolved.config.get("_legacy_provider"), "analytics")
        self.assertTrue(
            ServiceIntegration.objects.filter(
                school=self.school,
                service_name=resolved.service_name,
            ).exists()
        )

    def test_resolve_service_integration_no_backfill_when_disabled(self):
        Integration.objects.create(
            school=self.school,
            name="Legacy OIDC",
            slug="legacy-oidc",
            provider="analytics",
            category="OTHER",
            enabled=True,
            config={
                "service_hint": "oidc",
                "endpoint_url": "https://legacy.example.org/oidc",
            },
        )
        resolved = resolve_service_integration(
            self.school,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            service_name="oidc",
            name_hints=["oidc"],
            allow_legacy_backfill=False,
        )
        self.assertIsNone(resolved)
