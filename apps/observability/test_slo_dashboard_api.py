from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.events.models import (
    DomainEvent,
    WebhookDelivery as CanonicalWebhookDelivery,
    WebhookSubscription as CanonicalWebhookSubscription,
)
from apps.schools.models import School
from apps.siteconfig.models import (
    RegionConfig,
    SyncConflict,
    WebhookDelivery as LegacyWebhookDelivery,
    WebhookSubscription as LegacyWebhookSubscription,
)


class OperationalSLODashboardAPITests(TestCase):
    def setUp(self):
        self.region_us, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "date_format": "MM/DD/YYYY",
                "grading_scale": "0-100",
                "default_currency": "USD",
            },
        )
        self.region_cmr, _ = RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "default_language": "en",
                "timezone": "Africa/Douala",
                "date_format": "DD/MM/YYYY",
                "grading_scale": "0-20",
                "default_currency": "XAF",
            },
        )
        self.school_us = School.objects.create(
            name="US School",
            slug="us-school",
            subdomain="us-school",
            default_region=self.region_us,
            is_active=True,
        )
        self.school_cmr = School.objects.create(
            name="CMR School",
            slug="cmr-school",
            subdomain="cmr-school",
            default_region=self.region_cmr,
            is_active=True,
        )

        self.admin_user = User.objects.create_user(
            username="slo_admin",
            email="slo-admin@example.com",
            password="Test1234!",
            role="ADMIN",
            is_staff=True,
        )

    def _create_delivery(self, *, subscription, event_id: str, status: str, created_delta_seconds: int, completed_delta_seconds: int | None):
        now = timezone.now()
        delivery = LegacyWebhookDelivery.objects.create(
            subscription=subscription,
            event_id=event_id,
            event_type=subscription.event_type,
            status=status,
            attempts=1,
            max_attempts=4,
            delivered_at=now if status == LegacyWebhookDelivery.Status.DELIVERED else None,
            last_attempt_at=now if completed_delta_seconds is not None else None,
        )
        created_at = now - timedelta(seconds=created_delta_seconds)
        delivered_at = (
            now - timedelta(seconds=completed_delta_seconds)
            if completed_delta_seconds is not None
            else None
        )
        LegacyWebhookDelivery.objects.filter(pk=delivery.pk).update(
            created_at=created_at,
            delivered_at=delivered_at if status == LegacyWebhookDelivery.Status.DELIVERED else None,
            last_attempt_at=delivered_at,
        )
        return delivery

    def test_endpoint_returns_region_level_slo_metrics(self):
        subscription_us = LegacyWebhookSubscription.objects.create(
            school=self.school_us,
            event_type="grade.published",
            target_url="https://example.org/us-hook",
        )
        subscription_cmr = LegacyWebhookSubscription.objects.create(
            school=self.school_cmr,
            event_type="grade.published",
            target_url="https://example.org/cmr-hook",
        )

        self._create_delivery(
            subscription=subscription_us,
            event_id="us-1",
            status=LegacyWebhookDelivery.Status.DELIVERED,
            created_delta_seconds=3,
            completed_delta_seconds=1,
        )
        self._create_delivery(
            subscription=subscription_us,
            event_id="us-2",
            status=LegacyWebhookDelivery.Status.DELIVERED,
            created_delta_seconds=4,
            completed_delta_seconds=1,
        )
        self._create_delivery(
            subscription=subscription_cmr,
            event_id="cmr-1",
            status=LegacyWebhookDelivery.Status.DELIVERED,
            created_delta_seconds=50,
            completed_delta_seconds=1,
        )
        self._create_delivery(
            subscription=subscription_cmr,
            event_id="cmr-2",
            status=LegacyWebhookDelivery.Status.DEAD_LETTER,
            created_delta_seconds=60,
            completed_delta_seconds=1,
        )

        SyncConflict.objects.create(
            school=self.school_us,
            entity_type="attendance",
            entity_id=1,
            status=SyncConflict.Status.PENDING,
        )
        for idx in range(12):
            SyncConflict.objects.create(
                school=self.school_cmr,
                entity_type="evaluation",
                entity_id=100 + idx,
                status=SyncConflict.Status.PENDING,
            )
        SyncConflict.objects.create(
            school=self.school_cmr,
            entity_type="evaluation",
            entity_id=500,
            status=SyncConflict.Status.RESOLVED_SERVER,
        )

        self.client.force_login(self.admin_user)
        response = self.client.get("/api/observability/slo-dashboard/?hours=24")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["status"], "success")
        self.assertIn("slo_targets", payload)
        self.assertIn("regions", payload)
        self.assertGreaterEqual(payload["summary"]["regions"], 2)

        by_code = {row["region_code"]: row for row in payload["regions"]}
        self.assertIn("USA", by_code)
        self.assertIn("CMR", by_code)

        us = by_code["USA"]
        self.assertEqual(us["status"], "healthy")
        self.assertEqual(us["webhook"]["success_rate_percent"], 100.0)
        self.assertIn("remaining_percent", us["error_budget"])
        self.assertIn("pending", us["sync_conflicts"])

        cmr = by_code["CMR"]
        self.assertLess(cmr["webhook"]["success_rate_percent"], 99.0)
        self.assertGreater(
            cmr["sync_conflicts"]["pending"],
            payload["slo_targets"]["pending_sync_conflicts_max"],
        )
        self.assertIn(cmr["status"], {"warning", "critical"})

    def test_endpoint_aggregates_canonical_event_webhook_deliveries(self):
        event = DomainEvent.objects.create(
            event_type="billing.subscription_updated",
            payload={"plan": "platform-growth"},
            school_id=self.school_us.id,
        )
        canonical_subscription = CanonicalWebhookSubscription.objects.create(
            school_id=self.school_us.id,
            url="https://example.org/platform-hook",
            event_types=["billing.subscription_updated"],
            is_active=True,
        )
        now = timezone.now()
        delivery = CanonicalWebhookDelivery.objects.create(
            subscription=canonical_subscription,
            domain_event=event,
            status=CanonicalWebhookDelivery.Status.DELIVERED,
            attempted_at=now - timedelta(seconds=5),
            delivered_at=now - timedelta(seconds=1),
        )
        CanonicalWebhookDelivery.objects.filter(pk=delivery.pk).update(
            created_at=now - timedelta(seconds=10),
            attempted_at=now - timedelta(seconds=2),
            delivered_at=now - timedelta(seconds=1),
        )

        self.client.force_login(self.admin_user)
        response = self.client.get("/api/observability/slo-dashboard/?hours=24")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        by_code = {row["region_code"]: row for row in payload["regions"]}
        us = by_code["USA"]
        self.assertEqual(us["webhook"]["total"], 1)
        self.assertEqual(us["webhook"]["delivered"], 1)
        self.assertEqual(payload["webhook_stack"]["legacy_groups"], 0)

    def test_endpoint_requires_observability_auth(self):
        response = self.client.get("/api/observability/slo-dashboard/")
        self.assertEqual(response.status_code, 403)
