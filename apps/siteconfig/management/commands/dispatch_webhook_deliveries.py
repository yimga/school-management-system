"""Dispatch due outbound webhook deliveries from the canonical apps.events ledger."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from apps.events.webhooks import dispatch_due_webhooks


class Command(BaseCommand):
    help = "Dispatch due outbound webhook deliveries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=100, help="Max deliveries to process"
        )

    def handle(self, *args, **options):
        limit = max(1, int(options.get("limit") or 100))
        existing_tables = set(connection.introspection.table_names())
        if "events_webhookdelivery" not in existing_tables:
            self.stdout.write(
                self.style.WARNING(
                    "Canonical events WebhookDelivery table is not present. Apply migrations before dispatching webhooks."
                )
            )
            return
        started = timezone.now()
        results = dispatch_due_webhooks(limit=limit, now=started)
        delivered = sum(1 for r in results if r.get("status") == "delivered")
        retrying = sum(
            1 for r in results if r.get("status") == "pending" and not r.get("skipped")
        )
        dead = sum(1 for r in results if r.get("status") == "failed")

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed={len(results)} delivered={delivered} pending_retry={retrying} failed={dead}"
            )
        )
