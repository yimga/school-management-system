from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from apps.billing.renewal_reminders import (
    _DEFAULT_LIMIT,
    run_subscription_renewal_reminders,
)


class Command(BaseCommand):
    help = "Publish renewal/expiry reminders for soon-to-renew subscriptions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--as-of", help="Optional ISO datetime to run the reminder sweep against."
        )
        parser.add_argument(
            "--warning-days",
            type=int,
            default=None,
            help="Days before period end to remind (default: BILLING_RENEWAL_REMINDER_WARNING_DAYS or 7).",
        )
        parser.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the would-publish shape without emitting events/emails.",
        )

    def handle(self, *args, **options):
        as_of = parse_datetime(options["as_of"]) if options.get("as_of") else None
        summary = run_subscription_renewal_reminders(
            as_of=as_of,
            warning_days=options.get("warning_days"),
            limit=options["limit"],
            dry_run=options["dry_run"],
        )
        self.stdout.write(self.style.SUCCESS(f"Renewal reminder summary: {summary}"))
