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
from django.core.management.base import CommandError
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

    def test_school_with_only_retrying_row_is_drained(self):
        """Outer-loop fix (#1): a school whose only row is 'retrying' (a prior failed
        send, no newer 'pending') must still be enumerated and drained — otherwise its
        retry never runs (the dead-drainer one level up)."""
        row = OutboundMessageQueue.objects.create(
            school=self.school,
            channel=OutboundMessageQueue.Channel.WHATSAPP,
            recipient_identifier="+237600000010",
            body="retry me",
            status="retrying",
        )
        with patch("apps.communication.channels.send_whatsapp", return_value=True):
            self._run("--skip-email")  # no --school -> outer-loop enumeration path
        row.refresh_from_db()
        self.assertEqual(row.status, "sent")

    def test_school_scoped_drain_on_empty_queue_is_clean(self):
        """tuple->dict fix: `--school X` on an empty queue must not spuriously error
        (the empty per-school path used to return a bare (0,0) tuple -> .get() 500)."""
        out = self._run("--skip-email", "--school", str(self.school.id))
        self.assertIn("sms_whatsapp(sent=0", out)
        self.assertNotIn("ERRORS", out)

    def test_each_pending_row_sent_exactly_once(self):
        """#6 happy path: a single drain claims each row via its own claim stamp and
        sends it exactly once (the claim-stamp filter doesn't drop legitimately-claimed
        rows)."""
        for i in range(3):
            OutboundMessageQueue.objects.create(
                school=self.school, channel=OutboundMessageQueue.Channel.WHATSAPP,
                recipient_identifier=f"+23760000002{i}", body=f"m{i}", status="pending",
            )
        with patch("apps.communication.channels.send_whatsapp", return_value=True) as m:
            self._run("--skip-email")
        self.assertEqual(m.call_count, 3)
        self.assertEqual(
            OutboundMessageQueue.objects.filter(school=self.school, status="sent").count(), 3
        )

    def test_drain_surfaces_error_and_exits_nonzero(self):
        """#5: a drain failure must be distinguishable from an empty queue — the summary
        carries ERRORS=[...] and the command exits non-zero (CommandError)."""
        with patch(
            "apps.communication.tasks.process_outbound_message_queue",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(CommandError):
                call_command("drain_edge_outbox", "--skip-email", stdout=StringIO(), stderr=StringIO())

    def test_redrive_outbound_accepts_uuid_school(self):
        """#7: `redrive_outbound_messages --school <uuid>` no longer rejected by argparse
        (School.pk is a UUID; the old type=int made per-tenant redrive unusable)."""
        row = OutboundMessageQueue.objects.create(
            school=self.school, channel=OutboundMessageQueue.Channel.SMS,
            recipient_identifier="+237600000030", body="x", status="failed",
        )
        call_command("redrive_outbound_messages", "--school", str(self.school.id), stdout=StringIO())
        row.refresh_from_db()
        self.assertEqual(row.status, "pending")

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
