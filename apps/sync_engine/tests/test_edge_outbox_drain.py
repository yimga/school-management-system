"""Broker-less edge outbound-drain command (Tier 2 Slice B).

The sovereign / edge box has no Celery worker, so `drain_edge_outbox` runs the
email + SMS/WhatsApp drainers synchronously in-process, forwarding everything the
box queued while offline when connectivity returns.
"""
from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.communication.models import OutboundMessageQueue
from apps.schoolops.email_delivery import send_transactional
from apps.schoolops.models_email_deadletter import DeadLetterStatus, EmailDeadLetter
from apps.schools.models import School

_FAST = dict(
    SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF=[0],
    SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS=2,
)


@override_settings(**_FAST)
class DrainEdgeOutboxTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Edge {uid}", slug=f"edge-{uid}", subdomain=f"edge{uid}", is_active=True
        )

    def _run(self, *args):
        out, err = StringIO(), StringIO()
        call_command("drain_edge_outbox", *args, stdout=out, stderr=err)
        self._last_stderr = err.getvalue()
        return out.getvalue()

    @override_settings(RMC_EMAIL_OFFLINE_QUEUE=True)
    def test_email_queue_drained_and_forwarded(self):
        # Park an email offline (the guard writes a pending EmailDeadLetter row).
        send_transactional(subject="Hi", body="body", to=["p@example.com"], priority="transactional")
        self.assertEqual(EmailDeadLetter.objects.filter(status=DeadLetterStatus.PENDING).count(), 1)

        out = self._run("--skip-sms")

        self.assertIn("email(redriven=1", out)
        self.assertEqual(len(mail.outbox), 1)  # actually forwarded (locmem in tests)
        self.assertEqual(EmailDeadLetter.objects.filter(status=DeadLetterStatus.REDRIVEN).count(), 1)

    def test_whatsapp_queue_drained_and_sent(self):
        row = OutboundMessageQueue.objects.create(
            school=self.school,
            channel=OutboundMessageQueue.Channel.WHATSAPP,
            recipient_identifier="+237600000000",
            body="Attendance alert",
            status="pending",
        )
        with patch("apps.communication.channels.send_whatsapp", return_value=True) as m:
            out = self._run("--skip-email")
        self.assertTrue(m.called, f"send_whatsapp not called; stderr={self._last_stderr!r} out={out!r}")
        row.refresh_from_db()
        self.assertEqual(row.status, "sent")
        self.assertIsNotNone(row.sent_at)
        self.assertIn("sms_whatsapp(sent=1", out)

    @override_settings(RMC_EMAIL_OFFLINE_QUEUE=True)
    def test_both_queues_drained_in_one_run(self):
        send_transactional(subject="Hi", body="body", to=["q@example.com"], priority="transactional")
        OutboundMessageQueue.objects.create(
            school=self.school,
            channel=OutboundMessageQueue.Channel.WHATSAPP,
            recipient_identifier="+237600000001",
            body="msg",
            status="pending",
        )
        with patch("apps.communication.channels.send_whatsapp", return_value=True):
            out = self._run()
        self.assertIn("email(redriven=1", out)
        self.assertIn("sms_whatsapp(sent=1", out)

    def test_nothing_to_drain_is_clean(self):
        out = self._run()
        self.assertIn("drain_edge_outbox:", out)
        self.assertIn("redriven=0", out)
        self.assertIn("sent=0", out)

    def test_skip_both_is_a_noop(self):
        out = self._run("--skip-email", "--skip-sms")
        self.assertIn("nothing drained", out)

    def test_stale_processing_row_recovered_and_sent(self):
        """A row a dead run abandoned in 'processing' (updated_at > 15 min ago) is
        returned to the retry pool and forwarded. This stale-claim recovery was
        DEAD before OutboundMessageQueue gained `updated_at` — the drainer threw
        FieldError on every row, so nothing ever drained."""
        from datetime import timedelta

        from django.utils import timezone

        stale = OutboundMessageQueue.objects.create(
            school=self.school,
            channel=OutboundMessageQueue.Channel.WHATSAPP,
            recipient_identifier="+237600000002",
            body="stuck mid-send",
            status="processing",
        )
        # Force it stale — bulk update bypasses auto_now, exactly like a real claim.
        OutboundMessageQueue.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now() - timedelta(minutes=30)
        )
        # A fresh pending row makes the school eligible for a drain pass (the drainer
        # walks schools that have pending work); the stale row is recovered alongside it.
        OutboundMessageQueue.objects.create(
            school=self.school,
            channel=OutboundMessageQueue.Channel.WHATSAPP,
            recipient_identifier="+237600000003",
            body="fresh",
            status="pending",
        )
        with patch("apps.communication.channels.send_whatsapp", return_value=True):
            self._run("--skip-email")
        stale.refresh_from_db()
        self.assertEqual(stale.status, "sent")
