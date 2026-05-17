"""Renew calendar/mail push subscriptions before they expire.

Cron-friendly: exits 0 on success even if individual rows fail (errors are
logged + stored in each row's `config["push_subscription"]["last_renewal_error"]`).
Use --strict to exit 1 when any row failed.

Usage:
    python manage.py renew_push_subscriptions
    python manage.py renew_push_subscriptions --dry-run
    python manage.py renew_push_subscriptions --strict
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.integrations_marketplace.subscription_renewal import (
    renew_due_subscriptions,
)


class Command(BaseCommand):
    help = "Renew push subscriptions that are within the expiry window."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        results = renew_due_subscriptions(dry_run=opts["dry_run"])
        if opts["json"]:
            self.stdout.write(json.dumps(results, indent=2))
        else:
            counts: dict[str, int] = {}
            for r in results:
                counts[r.get("status") or "unknown"] = (
                    counts.get(r.get("status") or "unknown", 0) + 1
                )
            for status, n in sorted(counts.items()):
                self.stdout.write(f"  {status}: {n}")
            self.stdout.write(f"Total rows examined: {len(results)}")
        if opts["strict"]:
            failures = {"renewal_failed", "transport_error", "unauthorized",
                        "unhandled_exception"}
            if any(r.get("status") in failures for r in results):
                self.stderr.write("One or more renewals failed; exiting 1 (--strict).")
                raise SystemExit(1)
