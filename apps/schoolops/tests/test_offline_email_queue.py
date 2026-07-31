"""Offline email queue-and-forward (Tier 2 Slice A).

On a sovereign / offline edge box the default ``console.EmailBackend`` reports a
FALSE success and drops the mail. These tests prove that when the offline queue
is on, ``send_transactional`` PARKS the message durably in ``EmailDeadLetter``
instead — and that the box drains it (``redrive_dead_letters``) when it is back
online, WITHOUT re-parking a duplicate row on a still-offline retry (queue
amplification), and WITHOUT changing cloud behaviour when the queue is off.
"""
from __future__ import annotations

import smtplib

from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings

from apps.schoolops.email_delivery import redrive_dead_letters, send_transactional
from apps.schoolops.models_email_deadletter import DeadLetterStatus, EmailDeadLetter


class _FailingEmailBackend(BaseEmailBackend):
    """A backend that always raises — simulates an unreachable SMTP relay (still
    offline) so a redrive attempt fails and we can assert it does NOT re-park."""

    def send_messages(self, email_messages):  # noqa: D401
        raise smtplib.SMTPException("simulated offline SMTP failure")


_FAST = dict(  # single fast attempt, no real sleeps — keeps the failing paths quick
    SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF=[0],
    SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS=2,
)


@override_settings(RMC_EMAIL_OFFLINE_QUEUE=True, SCHOOLOPS_EMAIL_DLQ_ENABLED=False, **_FAST)
class OfflineEmailQueueTests(TestCase):
    """Offline queue ON via explicit flag (DLQ flag left OFF — the offline queue
    must enable the durable path by itself)."""

    def _send(self, **over):
        kwargs = dict(
            subject="Welcome to Gilead",
            body="Your account is ready.",
            to=["parent@example.com"],
            priority="transactional",
        )
        kwargs.update(over)
        return send_transactional(**kwargs)

    def test_offline_mode_parks_instead_of_sending(self):
        result = self._send()
        self.assertFalse(result["ok"])
        self.assertTrue(result["queued"])
        self.assertTrue(result.get("offline_queued"))
        # Nothing was actually delivered...
        self.assertEqual(len(mail.outbox), 0)
        # ...but the full payload is parked durably for later forward.
        rows = EmailDeadLetter.objects.filter(status=DeadLetterStatus.PENDING)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().error_kind, "offline_queued")

    def test_redrive_forwards_parked_message_when_online(self):
        self._send()  # park it
        self.assertEqual(EmailDeadLetter.objects.filter(status=DeadLetterStatus.PENDING).count(), 1)
        # Box is back online: redrive BYPASSES the offline guard (allow_offline_queue=False)
        # and attempts real delivery via the (locmem, in tests) backend.
        summary = redrive_dead_letters(limit=10)
        self.assertEqual(summary["redriven"], 1, summary)
        self.assertEqual(len(mail.outbox), 1)  # actually delivered now
        self.assertEqual(EmailDeadLetter.objects.filter(status=DeadLetterStatus.REDRIVEN).count(), 1)
        self.assertEqual(EmailDeadLetter.objects.filter(status=DeadLetterStatus.PENDING).count(), 0)

    def test_suppressed_recipient_offline_is_not_queued(self):
        from apps.schoolops.email_delivery import suppress_recipient

        suppress_recipient("bounced@example.com", reason="hard_bounce", source="test")
        result = self._send(to=["bounced@example.com"])
        self.assertTrue(result.get("suppressed"))
        self.assertFalse(result.get("offline_queued"))
        # Guard sits AFTER the suppression gate — a suppressed address is never parked.
        self.assertEqual(EmailDeadLetter.objects.count(), 0)


@override_settings(
    RMC_EMAIL_OFFLINE_QUEUE=True,
    EMAIL_BACKEND="apps.schoolops.tests.test_offline_email_queue._FailingEmailBackend",
    **_FAST,
)
class OfflineRedriveNoAmplificationTests(TestCase):
    def test_failed_redrive_does_not_amplify_queue(self):
        """A redrive that fails (still offline) must NOT spawn a second dead-letter
        row — it only bumps the original. Otherwise a long-offline box would grow
        one new pending row per drain cycle (exponential amplification)."""
        send_transactional(subject="s", body="b", to=["p@example.com"])  # park -> 1 row
        self.assertEqual(EmailDeadLetter.objects.count(), 1)

        summary = redrive_dead_letters(limit=10)  # attempt fails on the failing backend
        self.assertEqual(summary["redriven"], 0, summary)
        # STILL exactly one row — bumped, not amplified.
        self.assertEqual(EmailDeadLetter.objects.count(), 1)
        row = EmailDeadLetter.objects.get()
        self.assertEqual(row.status, DeadLetterStatus.PENDING)
        self.assertEqual(row.redrive_count, 1)


@override_settings(**_FAST)
class OfflineQueueGatingTests(TestCase):
    """The queue is OFF on the cloud (online profile / flag off) — send path unchanged."""

    def _send(self):
        return send_transactional(subject="s", body="b", to=["p@example.com"], priority="transactional")

    @override_settings(RMC_EMAIL_OFFLINE_QUEUE=False)
    def test_flag_off_sends_normally_no_park(self):
        result = self._send()
        self.assertTrue(result["ok"])
        self.assertFalse(result.get("offline_queued"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailDeadLetter.objects.count(), 0)

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge")
    def test_edge_profile_defaults_queue_on(self):
        # No explicit RMC_EMAIL_OFFLINE_QUEUE -> derives from the edge profile.
        result = self._send()
        self.assertTrue(result.get("offline_queued"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EmailDeadLetter.objects.filter(status=DeadLetterStatus.PENDING).count(), 1)

    @override_settings(RMC_DEPLOYMENT_PROFILE="online")
    def test_online_profile_sends_normally(self):
        result = self._send()
        self.assertTrue(result["ok"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailDeadLetter.objects.count(), 0)
