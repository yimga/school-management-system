"""Refresh OAuth access tokens for every active ServiceIntegration row.

Cron-friendly: exits 0 on success even if individual rows fail (errors are
logged + stored in each row's `config["last_refresh_error"]`). Use --strict
to exit 1 when any row failed.

Usage:
    python manage.py refresh_oauth_tokens
    python manage.py refresh_oauth_tokens --dry-run
    python manage.py refresh_oauth_tokens --strict
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.integrations_marketplace.token_refresh import refresh_due_oauth_tokens


class Command(BaseCommand):
    help = "Refresh OAuth access tokens that are within the expiry window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which rows would refresh; don't POST upstream.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 if any row refresh failed (refresh_failed / "
            "transport_error / deactivated_invalid_grant).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON instead of pretty output.",
        )

    def handle(self, *args, **opts):
        results = refresh_due_oauth_tokens(dry_run=opts["dry_run"])
        if opts["json"]:
            self.stdout.write(json.dumps(results, indent=2))
        else:
            counts: dict[str, int] = {}
            for r in results:
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            for status, n in sorted(counts.items()):
                self.stdout.write(f"  {status}: {n}")
            self.stdout.write(f"Total rows examined: {len(results)}")
        if opts["strict"]:
            failures = {
                "transport_error",
                "refresh_failed",
                "refresh_failed_no_token",
                "deactivated_invalid_grant",
                "unhandled_exception",
            }
            if any(r["status"] in failures for r in results):
                self.stderr.write("One or more rows failed; exiting 1 (--strict).")
                raise SystemExit(1)
