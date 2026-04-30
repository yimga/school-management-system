"""
Replay a persisted platform event: re-run in-process subscribers and optionally webhooks.

Usage::

    python manage.py replay_platform_event 123
    python manage.py replay_platform_event 123 --no-webhooks
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.event_bus import replay_event


class Command(BaseCommand):
    help = "Replay a PlatformEvent (PlatformEventLog) by primary key"

    def add_arguments(self, parser):
        parser.add_argument("event_id", type=int, help="PlatformEventLog / PlatformEvent primary key")
        parser.add_argument(
            "--no-webhooks",
            action="store_true",
            help="Only run in-process subscribers; do not enqueue webhook deliveries",
        )

    def handle(self, *args, **options):
        eid = int(options["event_id"])
        webhooks = not options["no_webhooks"]
        result = replay_event(eid, dispatch_webhooks=webhooks)
        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"Replayed event_id={eid}"))
        else:
            self.stderr.write(self.style.ERROR(result.get("error", "failed")))
