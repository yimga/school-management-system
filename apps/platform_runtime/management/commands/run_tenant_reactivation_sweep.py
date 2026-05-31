"""Run the 4-cadence tenant reactivation sweep (v4.00.98 Phase 4).

Usage:

    python manage.py run_tenant_reactivation_sweep                  # dry-run shape
    python manage.py run_tenant_reactivation_sweep --apply          # actually send emails
    python manage.py run_tenant_reactivation_sweep --apply --json   # machine-readable

Mirrors the Celery beat task. Safe to run from cron as a backstop when the
Celery worker is down.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the 4-cadence tenant reactivation sweep."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--apply", action="store_true", help="Actually send emails + persist attempts.")
        parser.add_argument("--limit-per-cadence", type=int, default=200)
        parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable lines.")

    def handle(self, *args, **options) -> None:
        from apps.platform_runtime.reactivation_engine import run_reactivation_sweep

        summary = run_reactivation_sweep(
            dry_run=not options.get("apply"),
            limit_per_cadence=int(options.get("limit_per_cadence") or 200),
        )
        if options.get("json"):
            self.stdout.write(json.dumps(summary, indent=2, default=str))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"Reactivation sweep ({'APPLY' if options.get('apply') else 'DRY RUN'})"
            ))
            self.stdout.write(f"  started_at:  {summary.get('started_at')}")
            self.stdout.write(f"  completed_at: {summary.get('completed_at')}")
            for cadence, data in (summary.get("per_cadence") or {}).items():
                self.stdout.write(
                    f"  [{cadence}] eligible={data.get('eligible_count')} "
                    f"sent={data.get('sent')} suppressed={data.get('suppressed')}"
                )
            self.stdout.write(
                f"  TOTAL sent={summary.get('total_sent')} suppressed={summary.get('total_suppressed')}"
            )
        # No sys.exit — Django mgmt commands signal "ok" by returning. Calling
        # sys.exit from inside call_command() would kill the parent process.
