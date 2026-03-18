"""
Send payment reminders for upcoming invoice due dates.
When CELERY_BROKER_URL is set, enqueues the task; otherwise runs the logic inline.
Use --dry-run to report what would be sent without sending.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.finance.tasks import run_payment_reminders, send_payment_reminders_task


class Command(BaseCommand):
    help = "Send payment reminders for upcoming invoice due dates. Use --dry-run to preview."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be sent without sending or updating reminders.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        broker_url = getattr(settings, "CELERY_BROKER_URL", None) or ""

        if broker_url and not dry_run:
            send_payment_reminders_task.delay(dry_run=False)
            self.stdout.write(
                self.style.SUCCESS(
                    "Payment reminders queued. Worker will process them."
                )
            )
            return
        if broker_url and dry_run:
            result = run_payment_reminders(dry_run=True)
        else:
            result = run_payment_reminders(dry_run=dry_run)

        if result.get("sent", 0) == 0 and result.get("count", 0) == 0:
            self.stdout.write(
                "No reminders due." if not dry_run else "No reminders would be sent."
            )
            return
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY RUN] Would send {result.get('sent', 0)} reminder(s) for {result.get('count', 0)} invoice(s). Channels: {result.get('channels', {})}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent {result.get('sent', 0)} reminder(s) for {result.get('count', 0)} invoice(s)."
                )
            )
