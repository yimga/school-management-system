from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.events.models import DomainEvent, WebhookDelivery, WebhookSubscription
from apps.events.webhooks import build_webhook_body
from apps.schools.models import School
from apps.siteconfig.webhook_delivery import (
    dispatch_due_webhooks,
    enqueue_webhook_event,
    replay_webhook_delivery,
    sign_payload,
)


class WebhookDeliveryServiceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Webhook Delivery School",
            slug="webhook-delivery-school",
            subdomain="webhook-delivery-school",
            is_active=True,
        )
        self.sub = WebhookSubscription.objects.create(
            school_id=self.school.id,
            url="https://example.org/webhook",
            event_types=["finance.aid_disbursed"],
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
        self.assertEqual(DomainEvent.objects.count(), 1)
        delivery = WebhookDelivery.objects.get()
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(delivery.domain_event.event_type, "finance.aid_disbursed")
        self.assertEqual(delivery.domain_event.payload["amount"], "50.00")

    def test_deliver_success_marks_delivered(self):
        delivery = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-success",
            data={"aid_id": 7},
        )[0]

        def _ok(url, body, headers, timeout):
            self.assertEqual(timeout, 30)
            self.assertEqual(url, self.sub.url)
            self.assertEqual(headers["X-Webhook-Event-Id"], str(delivery.domain_event.id))
            expected_sig = sign_payload(self.sub.secret, body)
            self.assertEqual(headers["X-Webhook-Signature"], expected_sig)
            self.assertEqual(body, build_webhook_body(delivery.domain_event))
            return 200, "ok"

        results = dispatch_due_webhooks(http_post=_ok, now=timezone.now())
        self.assertEqual(len(results), 1)

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.DELIVERED)
        self.assertEqual(delivery.retry_count, 0)
        self.assertIsNotNone(delivery.delivered_at)
        self.assertIsNone(delivery.scheduled_for)

    def test_retry_then_failed_after_max_attempts(self):
        delivery = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-fail",
            data={"aid_id": 8},
        )[0]
        delivery.max_attempts = 2
        delivery.save(update_fields=["max_attempts"])

        def _fail(url, body, headers, timeout):
            del url, body, headers, timeout
            return 503, "provider unavailable"

        now = timezone.now()
        dispatch_due_webhooks(http_post=_fail, now=now)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(delivery.retry_count, 1)
        self.assertIsNotNone(delivery.scheduled_for)

        dispatch_due_webhooks(http_post=_fail, now=delivery.scheduled_for + timedelta(seconds=1))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.FAILED)
        self.assertEqual(delivery.retry_count, 2)
        self.assertIsNone(delivery.scheduled_for)
        self.assertIn("503", delivery.error_message)

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
        later.scheduled_for = timezone.now() + timedelta(hours=2)
        later.save(update_fields=["scheduled_for"])

        called = {"count": 0}

        def _ok(url, body, headers, timeout):
            del url, body, headers, timeout
            called["count"] += 1
            return 204, ""

        dispatch_due_webhooks(http_post=_ok, now=timezone.now())
        due.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(called["count"], 1)
        self.assertEqual(due.status, WebhookDelivery.Status.DELIVERED)
        self.assertEqual(later.status, WebhookDelivery.Status.PENDING)

    def test_replay_creates_new_pending_delivery(self):
        original = enqueue_webhook_event(
            school=self.school,
            event_type="finance.aid_disbursed",
            event_id="evt-replay",
            data={"aid_id": 11},
        )[0]
        original.status = WebhookDelivery.Status.FAILED
        original.retry_count = 4
        original.save(update_fields=["status", "retry_count"])

        replay = replay_webhook_delivery(original)
        self.assertNotEqual(replay.domain_event_id, original.domain_event_id)
        self.assertEqual(replay.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(replay.retry_count, 0)
