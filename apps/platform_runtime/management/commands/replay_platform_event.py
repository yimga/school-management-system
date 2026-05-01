"""
Replay persisted platform events: single PK and/or filtered bulk (tenant, type, school).

Usage::

    python manage.py replay_platform_event 123
    python manage.py replay_platform_event 123 --no-webhooks
    python manage.py replay_platform_event --event-type=attendance_saved --tenant-id=5 --limit=50 --no-webhooks
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.platform_runtime.event_bus import replay_event, replay_events_filtered


class Command(BaseCommand):
    help = "Replay PlatformEventLog rows (subscribers + optional webhooks); supports filters for bulk replay"

    def add_arguments(self, parser):
        parser.add_argument(
            "event_id",
            nargs="?",
            type=int,
            default=None,
            help="Single PlatformEventLog primary key",
        )
        parser.add_argument(
            "--no-webhooks",
            action="store_true",
            help="Only run in-process subscribers; do not enqueue webhook deliveries",
        )
        parser.add_argument(
            "--event-type",
            dest="event_type",
            default=None,
            help="Bulk: limit to this event_type (newest first)",
        )
        parser.add_argument(
            "--tenant-id",
            dest="tenant_id",
            default=None,
            help="Bulk: filter tenant_id column",
        )
        parser.add_argument(
            "--school-id",
            dest="school_id",
            default=None,
            help="Bulk: filter school_id column",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Bulk: max rows to replay (default 100, cap 2000)",
        )

    def handle(self, *args, **options):
        webhooks = not options["no_webhooks"]
        eid = options["event_id"]
        et = options["event_type"]
        tid = options["tenant_id"]
        sid = options["school_id"]
        lim = int(options["limit"] or 100)

        if eid is not None:
            result = replay_event(eid, dispatch_webhooks=webhooks)
            if result.get("ok"):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Replayed event_id={eid} type={result.get('event_type')}"
                    )
                )
            else:
                raise CommandError(result.get("error", "failed"))
            return

        if not any([et, tid, sid]):
            raise CommandError(
                "Provide an event_id integer, or at least one of --event-type / --tenant-id / --school-id"
            )

        result = replay_events_filtered(
            event_type=et,
            tenant_id=tid,
            school_id=sid,
            dispatch_webhooks=webhooks,
            limit=lim,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Bulk replay: requested={result.get('requested')} replayed={result.get('replayed')} "
                f"failed={len(result.get('failed_ids') or [])}"
            )
        )
        failed = result.get("failed_ids") or []
        if failed:
            self.stderr.write(self.style.WARNING(f"failed_ids={failed[:20]}"))
