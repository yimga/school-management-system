from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from apps.billing.services import run_platform_billing_lifecycle


class Command(BaseCommand):
    help = "Run the platform billing lifecycle automation."

    def add_arguments(self, parser):
        parser.add_argument("--as-of", help="Optional ISO datetime to run the lifecycle against.")
        parser.add_argument("--grace-days", type=int, default=7)
        parser.add_argument("--suspension-days", type=int, default=30)

    def handle(self, *args, **options):
        as_of = parse_datetime(options["as_of"]) if options.get("as_of") else None
        summary = run_platform_billing_lifecycle(
            as_of=as_of,
            grace_days=options["grace_days"],
            suspension_days=options["suspension_days"],
        )
        self.stdout.write(self.style.SUCCESS(f"Billing lifecycle summary: {summary}"))
