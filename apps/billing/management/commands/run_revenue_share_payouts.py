from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.services import run_revenue_share_payout_execution


class Command(BaseCommand):
    help = "Execute due revenue-share payouts through configured platform billing processors."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Maximum number of payouts to execute.")
        parser.add_argument(
            "--include-failed",
            action="store_true",
            help="Retry payouts already marked as failed.",
        )

    def handle(self, *args, **options):
        summary = run_revenue_share_payout_execution(
            as_of=timezone.now(),
            limit=max(1, int(options.get("limit") or 50)),
            include_failed=bool(options.get("include_failed")),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "selected={selected} paid={paid} in_transit={in_transit} failed={failed} skipped={skipped}".format(
                    **summary
                )
            )
        )
