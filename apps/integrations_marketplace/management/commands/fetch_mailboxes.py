"""Fetch new messages for OAuth-connected mailboxes (gmail / outlook_mail).

Usage:
    python manage.py fetch_mailboxes
    python manage.py fetch_mailboxes --dry-run
    python manage.py fetch_mailboxes --strict
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.integrations_marketplace.mailbox_fetch import fetch_due_mailboxes


class Command(BaseCommand):
    help = "Fetch new messages for OAuth-connected mailboxes."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        results = fetch_due_mailboxes(dry_run=opts["dry_run"])
        if opts["json"]:
            self.stdout.write(json.dumps(results, indent=2))
        else:
            counts: dict[str, int] = {}
            delivered_total = 0
            for r in results:
                counts[r.get("status") or "unknown"] = (
                    counts.get(r.get("status") or "unknown", 0) + 1
                )
                delivered_total += int(r.get("delivered") or 0)
            for status, n in sorted(counts.items()):
                self.stdout.write(f"  {status}: {n}")
            self.stdout.write(f"Total rows examined: {len(results)}")
            self.stdout.write(f"Total new messages delivered: {delivered_total}")
        if opts["strict"]:
            failures = {"fetch_failed", "transport_error", "unauthorized",
                        "unhandled_exception"}
            if any(r.get("status") in failures for r in results):
                self.stderr.write("One or more fetches failed; exiting 1 (--strict).")
                raise SystemExit(1)
