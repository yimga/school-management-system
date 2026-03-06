from django.test import TestCase

from apps.events.legacy_bridge import (
    legacy_webhook_sync_snapshot,
    retire_legacy_webhook_subscriptions,
    sync_legacy_webhook_subscriptions,
)
from apps.events.models import WebhookSubscription as CanonicalWebhookSubscription
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig, WebhookSubscription as LegacyWebhookSubscription


class LegacyWebhookBridgeTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="BRG",
            name="Bridge Region",
            default_language="en",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-100",
            default_currency="USD",
        )
        self.school = School.objects.create(
            name="Bridge School",
            slug="bridge-school",
            subdomain="bridge-school",
            default_region=self.region,
            is_active=True,
        )

    def test_sync_aggregates_legacy_rows_into_canonical_subscription(self):
        LegacyWebhookSubscription.objects.create(
            school=self.school,
            event_type="student.enrolled",
            target_url="https://example.org/hook",
            secret="secret-a",
            is_active=True,
        )
        LegacyWebhookSubscription.objects.create(
            school=self.school,
            event_type="grade.published",
            target_url="https://example.org/hook",
            secret="secret-a",
            is_active=True,
        )

        result = sync_legacy_webhook_subscriptions(dry_run=False)
        self.assertEqual(result["created"], 1)
        canonical = CanonicalWebhookSubscription.objects.get()
        self.assertEqual(
            canonical.event_types,
            ["grade.published", "student.enrolled"],
        )
        self.assertTrue(canonical.is_active)

    def test_snapshot_reports_unsynced_groups_until_sync_runs(self):
        LegacyWebhookSubscription.objects.create(
            school=self.school,
            event_type="attendance.marked",
            target_url="https://example.org/attendance",
            secret="secret-b",
            is_active=True,
        )

        before = legacy_webhook_sync_snapshot()
        self.assertEqual(before["legacy_groups"], 1)
        self.assertEqual(before["unsynced_legacy_groups"], 1)

        sync_legacy_webhook_subscriptions(dry_run=False)

        after = legacy_webhook_sync_snapshot()
        self.assertEqual(after["unsynced_legacy_groups"], 0)

    def test_retire_legacy_webhooks_deactivates_legacy_subscriptions(self):
        LegacyWebhookSubscription.objects.create(
            school=self.school,
            event_type="student.promoted",
            target_url="https://example.org/promoted",
            secret="secret-c",
            is_active=True,
        )

        result = retire_legacy_webhook_subscriptions(dry_run=False)

        self.assertEqual(result["retired_active_subscriptions"], 1)
        self.assertFalse(LegacyWebhookSubscription.objects.get().is_active)
        snapshot = legacy_webhook_sync_snapshot()
        self.assertEqual(snapshot["legacy_active_groups"], 0)
