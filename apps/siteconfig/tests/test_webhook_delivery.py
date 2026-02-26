from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.schools.models import School
from apps.siteconfig.models import RegionConfig, WebhookDelivery, WebhookSubscription
from apps.siteconfig.webhook_delivery import (
    dispatch_due_webhooks,
    enqueue_webhook_event,
    replay_webhook_delivery,
    sign_payload,
)


class WebhookDeliveryServiceTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(code="WDS", name="Webhook Delivery Region")
        self.school = School.objects.create(
            name="Webhook Delivery School",
            slug="webhook-delivery-school",
            subdomain="webhook-delivery-school",
            default_region=self.region,
            is_active=True,
        )
        self.sub = WebhookSubscription.objects.create(
            school=self.school,
            event_type="finance.aid_disbursed",
            target_url="https://example.org/webhook",
            secret="super-secret",
            is_active=True,
        )

    def test_enqueue_is_idempotent_per_subscription_event(self):
        first = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-123",
            data={"amount": "50.00"},
        )
        second = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-123",
            data={"amount": "50.00"},
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(WebhookDelivery.objects.count(), 1)
        delivery = WebhookDelivery.objects.get()
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(delivery.event_id, "evt-123")
        self.assertEqual(delivery.payload["event_type"], "finance.aid_disbursed")
        self.assertTrue(delivery.signature.startswith("sha256="))

    def test_deliver_success_marks_delivered(self):
        delivery = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-success",
            data={"aid_id": 7},
        )[0]

        def _ok(url, body, headers):
            self.assertEqual(url, self.sub.target_url)
            self.assertEqual(headers["X-Webhook-Event-Id"], "evt-success")
            expected_sig = sign_payload(self.sub.secret, body)
            self.assertEqual(headers["X-Webhook-Signature"], expected_sig)
            return 200, "ok"

        results = dispatch_due_webhooks(http_post=_ok, now=timezone.now())
        self.assertEqual(len(results), 1)

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.DELIVERED)
        self.assertEqual(delivery.attempts, 1)
        self.assertIsNotNone(delivery.delivered_at)
        self.assertIsNone(delivery.next_attempt_at)

    def test_retry_then_dead_letter_after_max_attempts(self):
        delivery = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-fail",
            data={"aid_id": 8},
        )[0]
        delivery.max_attempts = 2
        delivery.save(update_fields=["max_attempts"])

        def _fail(url, body, headers):
            return 503, "provider unavailable"

        now = timezone.now()
        dispatch_due_webhooks(http_post=_fail, now=now)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.RETRYING)
        self.assertEqual(delivery.attempts, 1)
        self.assertIsNotNone(delivery.next_attempt_at)

        dispatch_due_webhooks(http_post=_fail, now=delivery.next_attempt_at + timedelta(seconds=1))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.DEAD_LETTER)
        self.assertEqual(delivery.attempts, 2)
        self.assertIsNone(delivery.next_attempt_at)
        self.assertIn("unavailable", delivery.last_error)

    def test_dispatch_only_processes_due_deliveries(self):
        due = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-due",
            data={"aid_id": 9},
        )[0]
        later = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-later",
            data={"aid_id": 10},
        )[0]
        later.next_attempt_at = timezone.now() + timedelta(hours=2)
        later.save(update_fields=["next_attempt_at"])

        called = {"count": 0}

        def _ok(url, body, headers):
            called["count"] += 1
            return 204, ""

        dispatch_due_webhooks(http_post=_ok, now=timezone.now())
        due.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(called["count"], 1)
        self.assertEqual(due.status, WebhookDelivery.Status.DELIVERED)
        self.assertIn(later.status, {WebhookDelivery.Status.PENDING, WebhookDelivery.Status.RETRYING})

    def test_replay_creates_new_pending_delivery(self):
        original = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-replay",
            data={"aid_id": 11},
        )[0]
        original.status = WebhookDelivery.Status.DEAD_LETTER
        original.attempts = 4
        original.save(update_fields=["status", "attempts"])

        replay = replay_webhook_delivery(original)
        self.assertNotEqual(replay.event_id, original.event_id)
        self.assertEqual(replay.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(replay.attempts, 0)

