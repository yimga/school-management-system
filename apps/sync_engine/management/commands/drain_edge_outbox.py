"""Drain the box's outbound queues to the outside world (Tier 2 Slice B).

A sovereign / offline edge box has NO Celery broker or worker, so the periodic
drainers that forward queued email and SMS/WhatsApp (wired into
``CELERY_BEAT_SCHEDULE``) never fire on it. This command runs those drainers
synchronously in-process, so the box forwards everything it queued while
offline with a single cron entry when connectivity returns::

    */5 * * * *  python manage.py drain_edge_outbox

Two independent queues are drained, each best-effort — a failure in one never
stops the other, and neither raises into the cron:

  * **Email** -> :func:`apps.schoolops.email_delivery.redrive_dead_letters`
    (the ``EmailDeadLetter`` queue the offline-email guard parks into).
  * **SMS / WhatsApp** -> :func:`apps.communication.tasks.process_outbound_message_queue`
    (the ``OutboundMessageQueue`` the SMS/WhatsApp auto-enqueue parks into) —
    called directly, which executes synchronously without a broker.

Idempotent: a row that still fails to forward (box briefly online, then the
provider is unreachable) stays queued and is retried next run; each queue's own
``redrive_count`` / ``retry_count`` bounds the attempts.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Drain the edge box's outbound email + SMS/WhatsApp queues "
        "(broker-less forward-when-online)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=50,
            help="Max rows to forward per queue per run (default 50).",
        )
        parser.add_argument(
            "--school", default=None,
            help="Restrict the SMS/WhatsApp drain to a single school id.",
        )
        parser.add_argument(
            "--skip-email", action="store_true",
            help="Do not drain the email dead-letter queue.",
        )
        parser.add_argument(
            "--skip-sms", action="store_true",
            help="Do not drain the SMS/WhatsApp outbound queue.",
        )

    def handle(self, *args, **options):
        limit = max(1, int(options.get("limit") or 50))
        school = options.get("school")
        skip_email = bool(options.get("skip_email"))
        skip_sms = bool(options.get("skip_sms"))

        email_summary = None if skip_email else self._drain_email(limit)
        sms_summary = None if skip_sms else self._drain_sms(limit, school)

        parts = []
        if email_summary is not None:
            parts.append(
                "email(redriven={redriven} still_pending={still_pending} "
                "exhausted={exhausted} abandoned={abandoned} enabled={enabled})".format(
                    redriven=email_summary.get("redriven", 0),
                    still_pending=email_summary.get("still_pending", 0),
                    exhausted=email_summary.get("exhausted", 0),
                    abandoned=email_summary.get("abandoned", 0),
                    enabled=email_summary.get("enabled", False),
                )
            )
        if sms_summary is not None:
            parts.append(
                "sms_whatsapp(sent={sent} failed={failed} processed={processed})".format(
                    sent=sms_summary.get("sent", 0),
                    failed=sms_summary.get("failed", 0),
                    processed=sms_summary.get("processed", 0),
                )
            )
        self.stdout.write(
            "drain_edge_outbox: "
            + (" ".join(parts) if parts else "nothing drained (both queues skipped)")
        )

    def _drain_email(self, limit):
        try:
            from apps.schoolops.email_delivery import redrive_dead_letters

            return redrive_dead_letters(limit=limit)
        except Exception as exc:  # never crash the cron on one queue's failure
            self.stderr.write(
                f"drain_edge_outbox: email drain error {type(exc).__name__}: {exc}"
            )
            return {"redriven": 0, "still_pending": 0, "exhausted": 0,
                    "abandoned": 0, "enabled": False, "error": type(exc).__name__}

    def _drain_sms(self, limit, school):
        try:
            from apps.communication.tasks import process_outbound_message_queue

            # A @shared_task called directly runs synchronously in-process — no
            # broker needed, which is exactly the broker-less edge box.
            return process_outbound_message_queue(school_id=school, limit=limit)
        except Exception as exc:  # never crash the cron on one queue's failure
            self.stderr.write(
                f"drain_edge_outbox: sms/whatsapp drain error {type(exc).__name__}: {exc}"
            )
            return {"sent": 0, "failed": 0, "processed": 0, "error": type(exc).__name__}
