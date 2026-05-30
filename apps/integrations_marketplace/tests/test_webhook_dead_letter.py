"""v4.00.92 — Unit tests for ``webhook_dead_letter`` (W11 module).

Wraps the ``WebhookDeadLetter`` SOT model. Uses ``django.test.TestCase``
because rows are written to (and read from) the DB inside each test;
TestCase wraps every test in a transaction that rolls back at teardown so
no row-leak risk across cases.

Coverage:
  * enqueue_dead_letter -> creates a pending row w/ b64 payload
  * list_due -> filters by status + ordering
  * mark_replayed -> flips pending->replayed
  * sweep_expired_due -> flips expired pending->expired
  * decode_payload -> b64 round-trip
  * DEFAULT_EXPIRY_SECONDS constant value
"""

from __future__ import annotations

import base64
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.integrations_marketplace import webhook_dead_letter as _dlq
from apps.integrations_marketplace.models import WebhookDeadLetter


class WebhookDeadLetterTests(TestCase):

    def test_default_expiry_seconds_is_seven_days(self):
        """DEFAULT_EXPIRY_SECONDS constant matches the module's 7d documentation."""
        self.assertEqual(_dlq.DEFAULT_EXPIRY_SECONDS, 7 * 24 * 60 * 60)

    def test_enqueue_dead_letter_creates_pending_row(self):
        """enqueue persists a row w/ b64-encoded payload + status=pending."""
        row = _dlq.enqueue_dead_letter(
            provider="schoology",
            event_type="grade.posted",
            payload=b'{"event":"x"}',
            reason="exhausted_after_6_retries",
            tenant_schema="acme",
            attempt_count=6,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.provider, "schoology")
        self.assertEqual(row.status, "pending")
        self.assertEqual(row.attempt_count, 6)
        # b64-encoded.
        decoded = base64.b64decode(row.payload_b64.encode("ascii"))
        self.assertEqual(decoded, b'{"event":"x"}')

    def test_list_due_filters_by_status(self):
        """list_due returns only matching status rows, oldest-first."""
        # One pending + one already-replayed.
        _dlq.enqueue_dead_letter(
            provider="schoology", event_type="g.p", payload=b"1",
            tenant_schema="acme",
        )
        replayed = _dlq.enqueue_dead_letter(
            provider="d2l", event_type="g.p", payload=b"2",
            tenant_schema="acme",
        )
        # Manually flip the second to replayed via the helper.
        self.assertTrue(_dlq.mark_replayed(replayed.pk))
        # list_due default status="pending" should NOT return the replayed one.
        pending = _dlq.list_due()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].status, "pending")
        # list_due(status="replayed") returns the other.
        replayed_list = _dlq.list_due(status="replayed")
        self.assertEqual(len(replayed_list), 1)
        self.assertEqual(replayed_list[0].pk, replayed.pk)

    def test_mark_replayed_flips_status(self):
        """mark_replayed flips pending->replayed + stamps last_attempted_at."""
        row = _dlq.enqueue_dead_letter(
            provider="schoology", event_type="g.p", payload=b"x",
            tenant_schema="acme",
        )
        self.assertEqual(row.status, "pending")
        self.assertTrue(_dlq.mark_replayed(row.pk))
        # Re-fetch + verify.
        row.refresh_from_db()
        self.assertEqual(row.status, "replayed")
        self.assertIsNotNone(row.last_attempted_at)
        # Replaying again is a no-op (row no longer pending).
        self.assertFalse(_dlq.mark_replayed(row.pk))

    def test_sweep_expired_due_filters_correctly(self):
        """sweep flips pending rows past expires_at to expired."""
        # Past-expiry row.
        past_row = _dlq.enqueue_dead_letter(
            provider="schoology", event_type="g.p", payload=b"1",
            tenant_schema="acme",
        )
        # Force expires_at into the past.
        WebhookDeadLetter.objects.filter(pk=past_row.pk).update(
            expires_at=timezone.now() - timedelta(seconds=60),
        )
        # Fresh row (expiry in the future, default 7d).
        _dlq.enqueue_dead_letter(
            provider="d2l", event_type="g.p", payload=b"2",
            tenant_schema="acme",
        )
        n = _dlq.sweep_expired_due()
        self.assertEqual(n, 1)
        past_row.refresh_from_db()
        self.assertEqual(past_row.status, "expired")
        # The fresh row stayed pending.
        fresh_pending = WebhookDeadLetter.objects.filter(
            status="pending", provider="d2l",
        ).count()
        self.assertEqual(fresh_pending, 1)

    def test_decode_payload_round_trip(self):
        """decode_payload returns the original bytes from the b64 column."""
        original = b'{"deeply": "nested\\u00e9 unicode bytes"}'
        row = _dlq.enqueue_dead_letter(
            provider="schoology", event_type="g.p", payload=original,
            tenant_schema="acme",
        )
        self.assertEqual(_dlq.decode_payload(row), original)
