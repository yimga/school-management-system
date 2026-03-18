"""
Apply split-billing late fees for overdue payer shares.
Queues Celery task when broker is configured; runs inline otherwise.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.finance.tasks import apply_split_late_fees_task, run_split_late_fees


class Command(BaseCommand):
    help = "Apply overdue late fees to split-billing payer shares. Use --dry-run to preview."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be applied without persisting changes.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        broker_url = getattr(settings, "CELERY_BROKER_URL", None) or ""

        if broker_url and not dry_run:
            apply_split_late_fees_task.delay(dry_run=False)
            self.stdout.write(
                self.style.SUCCESS(
                    "Split late-fee task queued. Worker will process it."
                )
            )
            return

        result = run_split_late_fees(dry_run=dry_run)
        if result.get("status") == "disabled":
            self.stdout.write(
                "Split late fee policy is disabled in backend feature flags."
            )
            return

        applied = int(result.get("applied", 0) or 0)
        checked = int(result.get("checked", 0) or 0)
        total_fee = result.get("total_fee", "0.00")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY RUN] Would apply {applied} late fee(s) across {checked} payer share(s); total={total_fee}."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Applied {applied} late fee(s) across {checked} payer share(s); total={total_fee}."
                )
            )
