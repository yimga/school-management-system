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

NOTE — ``python manage.py run_periodic_jobs`` is the MORE COMPLETE beat-less drain:
it runs the whole in-process periodic registry (this SMS/WhatsApp queue AND the email
DLQ AND ``events.process_event_outbox`` — the internal-subscriber/webhook drainer this
command does NOT cover — plus reminders and monitors), each at its own cadence with
per-job locking. Prefer cronning ``run_periodic_jobs`` on a bare box; use this focused
command when you only want to force email + SMS/WhatsApp forwarding.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


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
            # A backend-blocked drain returns all-zero counters, which is exactly
            # the shape of "queue was empty" — the failure mode this command's
            # error handling already exists to prevent. Say it out loud instead.
            blocked = int(email_summary.get("blocked_no_backend", 0) or 0)
            if blocked:
                parts.append(
                    f"EMAIL NOT DELIVERED: {blocked} message(s) still parked because "
                    "EMAIL_BACKEND cannot deliver (console/locmem/dummy). They are "
                    "intact and forward once an SMTP relay or local MTA is configured."
                )
        if sms_summary is not None:
            parts.append(
                "sms_whatsapp(sent={sent} failed={failed} processed={processed})".format(
                    sent=sms_summary.get("sent", 0),
                    failed=sms_summary.get("failed", 0),
                    processed=sms_summary.get("processed", 0),
                )
            )

        # Surface a drain FAILURE distinctly — otherwise a broken drain reads exactly
        # like an empty queue (sent=0/redriven=0) and exits 0, so a cron that watches the
        # exit code or stdout sees a silent failure as "clean".
        errors = []
        if email_summary and email_summary.get("error"):
            errors.append("email:" + str(email_summary["error"]))
        if sms_summary and sms_summary.get("error"):
            errors.append("sms_whatsapp:" + str(sms_summary["error"]))

        line = "drain_edge_outbox: " + (
            " ".join(parts) if parts else "nothing drained (both queues skipped)"
        )
        if errors:
            line += " ERRORS=[" + ", ".join(errors) + "]"
        self.stdout.write(line)
        if errors:
            raise CommandError(f"{len(errors)} queue(s) failed to drain: {', '.join(errors)}")

    def _drain_email(self, limit):
        try:
            from apps.schoolops.email_delivery import redrive_dead_letters

            return redrive_dead_letters(limit=limit)
        except Exception as exc:  # never crash the cron on one queue's failure
            self.stderr.write(
                f"drain_edge_outbox: email drain error {type(exc).__name__}: {exc}"
            )
            return {"redriven": 0, "still_pending": 0, "exhausted": 0,
                    "abandoned": 0, "enabled": False, "blocked_no_backend": 0,
                    "error": type(exc).__name__}

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
