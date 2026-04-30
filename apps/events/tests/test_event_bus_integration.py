"""Event bus, outbox processing, retries, and replay."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.events.bus import (
    clear_subscribers_for_tests,
    publish,
    subscribe,
)
from apps.events.models import DomainEvent, WebhookDelivery, WebhookSubscription
from apps.events.tasks import process_outbox_batch
from apps.events.webhooks import deliver_webhook_delivery


class EventBusPublishSubscribeTests(TestCase):
    def tearDown(self):
        clear_subscribers_for_tests()
        super().tearDown()

    def test_publish_returns_domain_event(self):
        ev = publish("debug.echo", {"x": 1}, school_id=None)
        self.assertIsInstance(ev, DomainEvent)
        self.assertEqual(ev.event_type, "debug.echo")
        self.assertEqual(ev.payload.get("x"), 1)

    def test_subscriber_invoked_on_outbox_process(self):
        seen: list[str] = []

        def handler(event):
            seen.append(event.event_type)

        subscribe("student.created", handler)
        publish("student.created", {"student_id": "1", "school_id": None}, school_id=None)
        n = process_outbox_batch(batch_size=10)
        self.assertGreaterEqual(n, 1)
        self.assertIn("student.created", seen)

    def test_wildcard_subscriber(self):
        kinds: list[str] = []

        def catch_all(event):
            kinds.append(event.event_type)

        subscribe("*", catch_all)
        publish("workflow.triggered", {"workflow_key": "x"}, school_id=None)
        process_outbox_batch(batch_size=10)
        self.assertIn("workflow.triggered", kinds)


class WebhookRetryDeadLetterTests(TestCase):
    def test_delivery_retries_then_dead_letter(self):
        school = uuid.uuid4()
        sub = WebhookSubscription.objects.create(
            school_id=school,
            url="https://example.invalid/webhook",
            event_types=["payment.received"],
            secret="s",
            is_active=True,
        )
        ev = DomainEvent.objects.create(
            event_type="payment.received",
            payload={"payment_id": "p1", "school_id": str(school)},
            school_id=school,
            status=DomainEvent.Status.PENDING,
        )
        d = WebhookDelivery.objects.create(
            subscription=sub,
            domain_event=ev,
            status=WebhookDelivery.Status.PENDING,
            scheduled_for=timezone.now(),
            max_attempts=2,
        )

        def always_fail(url, body, headers, timeout):
            return 500, "no"

        now1 = timezone.now()
        r1 = deliver_webhook_delivery(d, http_post=always_fail, now=now1)
        d.refresh_from_db()
        self.assertEqual(r1["status"], WebhookDelivery.Status.PENDING)
        self.assertEqual(d.retry_count, 1)

        # Retry is scheduled in the future; advance past scheduled_for for next attempt.
        now2 = (d.scheduled_for or now1) + timedelta(seconds=1)
        deliver_webhook_delivery(d, http_post=always_fail, now=now2)
        d.refresh_from_db()
        self.assertEqual(d.status, WebhookDelivery.Status.FAILED)
        self.assertTrue(d.is_dead_letter)


class ReplayCommandSmokeTests(TestCase):
    def test_replay_clones_pending_row(self):
        ev = DomainEvent.objects.create(
            event_type="grade.published",
            payload={"school_id": "x"},
            school_id=None,
            status=DomainEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )
        from django.core.management import call_command

        call_command("replay_domain_events", str(ev.id))
        dup = DomainEvent.objects.exclude(pk=ev.pk).order_by("-created_at").first()
        self.assertIsNotNone(dup)
        self.assertEqual(dup.event_type, "grade.published")
        self.assertEqual(dup.status, DomainEvent.Status.PENDING)
