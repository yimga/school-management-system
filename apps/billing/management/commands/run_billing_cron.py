"""Single daily entrypoint for ALL platform-billing automation.

The billing automation is normally driven by Celery beat
(``apps.billing.beat_schedule``). When a deployment has no reliable beat worker
(the scheduler has historically gone dark), wiring ONE cron line to this command
keeps billing autonomous regardless of mechanism — system cron, Render cron, a
CI cron, or a manual run all work:

    python manage.py run_billing_cron

It runs, in order: the billing lifecycle (trial conversion, renewal charges +
invoices + tax, past-due aging, suspend/restore), then renewal reminders, then
trial-ending reminders. Each step is independently safe and idempotent, so
re-running the command never double-charges, double-issues, or double-emails.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from apps.billing.renewal_reminders import (
    run_subscription_renewal_reminders,
    run_trial_ending_reminders,
)
from apps.billing.services import run_platform_billing_lifecycle


class Command(BaseCommand):
    help = "Run all daily platform-billing automation (lifecycle + reminders) in one pass."

    def add_arguments(self, parser):
        parser.add_argument(
            "--as-of", help="Optional ISO datetime to run the automation against."
        )
        parser.add_argument("--grace-days", type=int, default=7)
        parser.add_argument("--suspension-days", type=int, default=30)
        parser.add_argument(
            "--warning-days",
            type=int,
            default=None,
            help="Reminder window (default: BILLING_RENEWAL_REMINDER_WARNING_DAYS or 7).",
        )

    def handle(self, *args, **options):
        as_of = parse_datetime(options["as_of"]) if options.get("as_of") else None
        warning_days = options.get("warning_days")
        summary = {
            "lifecycle": run_platform_billing_lifecycle(
                as_of=as_of,
                grace_days=options["grace_days"],
                suspension_days=options["suspension_days"],
            ),
            "renewal_reminders": run_subscription_renewal_reminders(
                as_of=as_of, warning_days=warning_days
            ),
            "trial_reminders": run_trial_ending_reminders(
                as_of=as_of, warning_days=warning_days
            ),
        }
        self.stdout.write(self.style.SUCCESS(f"Billing cron summary: {summary}"))
