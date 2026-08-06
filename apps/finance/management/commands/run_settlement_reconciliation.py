"""Roll up recorded payments into finance.PaymentReconciliation.

Defaults to a DRY RUN (nothing written) — pass --apply to persist rows.
When CELERY_BROKER_URL is set and --apply is used, the work is queued;
otherwise it runs inline synchronously across active tenants.

Examples:
  manage.py run_settlement_reconciliation                 # dry-run, prev month
  manage.py run_settlement_reconciliation --apply         # persist prev month
  manage.py run_settlement_reconciliation --start 2026-07-01 --end 2026-07-31 --apply
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Reconcile recorded payments per (region, payment method, period) into "
        "PaymentReconciliation. Dry-run by default; use --apply to persist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--start", help="Period start YYYY-MM-DD (default: previous calendar month)."
        )
        parser.add_argument(
            "--end", help="Period end YYYY-MM-DD (default: previous calendar month)."
        )
        parser.add_argument(
            "--school-id", help="Reconcile a single school by id (default: all active)."
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist PaymentReconciliation rows (default is a dry run).",
        )

    def handle(self, *args, **options):
        from apps.finance.tasks import run_settlement_reconciliation_task

        dry_run = not options.get("apply")
        kwargs = {
            "dry_run": dry_run,
            "period_start": options.get("start"),
            "period_end": options.get("end"),
        }
        if options.get("school_id"):
            kwargs["school_id"] = options["school_id"]

        broker_url = getattr(settings, "CELERY_BROKER_URL", None) or ""
        if broker_url and not dry_run:
            run_settlement_reconciliation_task.delay(**kwargs)
            self.stdout.write(
                self.style.SUCCESS(
                    "Settlement reconciliation queued. Worker will process it."
                )
            )
            return

        result = run_settlement_reconciliation_task.apply(kwargs=kwargs).get()
        self.stdout.write(json.dumps(result, indent=2, default=str))
        if dry_run:
            self.stdout.write(
                self.style.WARNING("[DRY RUN] No rows written — pass --apply to persist.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Wrote {result.get('written', 0)} reconciliation row(s); "
                    f"{result.get('discrepancies', 0)} flagged with a discrepancy."
                )
            )
