"""
Event bus: publish, subscribers, webhooks, retries/replay.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.platform_runtime.models import (
    EventWebhookDelivery,
    EventWebhookSubscription,
    PlatformEventLog,
)
from apps.platform_runtime import event_bus
from apps.platform_runtime.tasks import deliver_event_webhook_task


def _clear_handler(event_type: str, fn) -> None:
    lst = event_bus._SUBSCRIBERS.get(event_type)
    if lst and fn in lst:
        lst.remove(fn)


class EventBusPublishSubscriberTests(TestCase):
    def test_publish_persists_and_calls_subscriber(self):
        seen = []

        def handler(payload, **kwargs):
            seen.append((payload.get("msg"), kwargs.get("event_type")))

        event_bus.register_subscriber("bus.test_ping", handler)
        try:
            row = event_bus.publish_event("bus.test_ping", {"msg": "hello"})
            self.assertIsNotNone(row)
            self.assertEqual(PlatformEventLog.objects.filter(pk=row.pk).count(), 1)
            self.assertEqual(seen, [("hello", "bus.test_ping")])
        finally:
            _clear_handler("bus.test_ping", handler)

    def test_publish_event_merges_correlation_actor_source(self):
        row = event_bus.publish_event(
            "bus.test_ping",
            {"msg": "meta"},
            correlation_id="corr-sweep",
            actor={"user_id": 1},
            source="contract_sweep",
        )
        self.assertIsNotNone(row)
        row.refresh_from_db()
        self.assertEqual(row.payload.get("correlation_id"), "corr-sweep")
        self.assertEqual(row.payload.get("source"), "contract_sweep")
        self.assertEqual(row.payload.get("actor"), {"user_id": 1})

    def test_replay_invokes_subscriber(self):
        row = event_bus.publish_event("bus.test_ping", {"msg": "once"})
        self.assertIsNotNone(row)
        seen = []

        def handler(payload, **kwargs):
            if kwargs.get("is_replay"):
                seen.append(payload.get("msg"))

        event_bus.register_subscriber("bus.test_ping", handler)
        try:
            out = event_bus.replay_event(row.pk, dispatch_webhooks=False)
            self.assertTrue(out.get("ok"))
            self.assertEqual(seen, ["once"])
            audit = (
                PlatformEventLog.objects.filter(event_type="platform_event_replayed")
                .order_by("-pk")
                .first()
            )
            self.assertIsNotNone(audit)
            self.assertEqual(audit.payload.get("source_event_id"), str(row.pk))
        finally:
            _clear_handler("bus.test_ping", handler)

    def test_replay_events_filtered_runs_all_matching(self):
        event_bus.publish_event("bus.test_ping", {"msg": "a"})
        event_bus.publish_event("bus.test_ping", {"msg": "b"})
        n = PlatformEventLog.objects.filter(event_type="bus.test_ping").count()
        out = event_bus.replay_events_filtered(
            event_type="bus.test_ping", dispatch_webhooks=False, limit=10
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("failed_ids"), [])
        self.assertEqual(out.get("requested"), n)
        self.assertEqual(out.get("replayed"), n)


class EventBusWebhookTests(TestCase):
    def setUp(self):
        super().setUp()
        self._delay_patch = patch.object(
            deliver_event_webhook_task,
            "delay",
            side_effect=self._sync_deliver,
        )
        self._delay_patch.start()

    def tearDown(self):
        self._delay_patch.stop()
        super().tearDown()

    @staticmethod
    def _sync_deliver(delivery_id: int):
        return event_bus.deliver_webhook_attempt(int(delivery_id))

    @patch("requests.post")
    def test_webhook_post_delivers_json(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        EventWebhookSubscription.objects.create(
            target_url="https://example.invalid/hook",
            event_types=["bus.test_ping"],
            is_active=True,
        )
        event_bus.publish_event("bus.test_ping", {"msg": "webhook"})
        self.assertTrue(mock_post.called)
        url = mock_post.call_args[0][0]
        self.assertIn("example.invalid", url)
        d = EventWebhookDelivery.objects.first()
        self.assertIsNotNone(d)
        self.assertEqual(d.status, EventWebhookDelivery.Status.DELIVERED)


class EventBusRetryDeadLetterTests(TestCase):
    def test_dead_letter_after_max_attempts(self):
        sub = EventWebhookSubscription.objects.create(
            target_url="https://example.invalid/hook",
            event_types=["bus.test_ping"],
            is_active=True,
        )
        ev = PlatformEventLog.objects.create(
            event_type="bus.test_ping",
            payload={"msg": "x"},
        )
        d = EventWebhookDelivery.objects.create(
            subscription=sub,
            platform_event=ev,
            status=EventWebhookDelivery.Status.PENDING,
        )
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=500, text="err")
            with patch.object(event_bus, "MAX_WEBHOOK_ATTEMPTS", 3):
                with patch.object(event_bus, "WEBHOOK_BACKOFF_SECONDS", (0, 0, 0)):
                    with patch.object(
                        deliver_event_webhook_task,
                        "apply_async",
                        side_effect=lambda args=None, **kw: event_bus.deliver_webhook_attempt(
                            args[0]
                        ),
                    ):
                        for _ in range(5):
                            event_bus.deliver_webhook_attempt(d.pk)
                            d.refresh_from_db()
                            if d.status == EventWebhookDelivery.Status.DEAD_LETTER:
                                break
        d.refresh_from_db()
        self.assertEqual(d.status, EventWebhookDelivery.Status.DEAD_LETTER)
        self.assertGreaterEqual(d.attempt_count, 3)
