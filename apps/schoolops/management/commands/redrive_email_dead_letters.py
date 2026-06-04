"""Redrive parked email dead-letter sends (audit residual closeout).

Re-attempts transactional sends that permanently failed for a transient
reason and were parked in :class:`apps.schoolops.models_email_deadletter.EmailDeadLetter`
(requires ``SCHOOLOPS_EMAIL_DLQ_ENABLED``). Safe to run on a schedule.

    python manage.py redrive_email_dead_letters            # redrive up to 50
    python manage.py redrive_email_dead_letters --limit 200

Each row is re-sent with a fresh idempotency key, suppression is honoured, and
rows that exhaust ``SCHOOLOPS_EMAIL_DLQ_MAX_REDRIVES`` (default 5) are marked
``exhausted``. Prints a one-line summary; never raises.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Redrive parked email dead-letter sends (SCHOOLOPS_EMAIL_DLQ_ENABLED)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        from apps.schoolops.email_delivery import redrive_dead_letters

        limit = int(options.get("limit") or 50)
        summary = redrive_dead_letters(limit=limit)
        if not summary.get("enabled"):
            self.stdout.write(
                "DLQ disabled (set SCHOOLOPS_EMAIL_DLQ_ENABLED=1 to enable). "
                "Nothing redriven."
            )
            return
        self.stdout.write(
            "redrive: scanned={scanned} redriven={redriven} "
            "still_pending={still_pending} exhausted={exhausted} "
            "abandoned={abandoned}".format(**summary)
        )
