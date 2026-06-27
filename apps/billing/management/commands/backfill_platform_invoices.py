from django.core.management.base import BaseCommand

from apps.billing.services import backfill_platform_invoices


class Command(BaseCommand):
    help = "Issue numbered PlatformInvoices for historical renewal charges that predate the invoice layer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional cap on the number of historical charges to process.",
        )

    def handle(self, *args, **options):
        summary = backfill_platform_invoices(limit=options.get("limit"))
        self.stdout.write(self.style.SUCCESS(f"Invoice backfill summary: {summary}"))
