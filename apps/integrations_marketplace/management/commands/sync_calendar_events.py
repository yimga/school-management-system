"""Manually run the calendar event-sync sweep (ops / smoke).

Pushes upcoming published ``SchoolEvent`` rows to each active tenant's
connected Google / Outlook calendar — the same work the
``integrations_marketplace.sync_calendar_events`` beat task does. Useful to run
by hand after connecting a calendar, or to verify a tenant's sync.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Push upcoming published school events to connected tenant calendars."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id",
            type=int,
            default=None,
            help="Sweep only this school (inside its tenant context).",
        )

    def handle(self, *args, **options):
        from apps.integrations_marketplace.calendar_sync import (
            _sync_calendar_events_all_tenants,
            sync_school_events,
        )

        school_id = options.get("school_id")
        if school_id:
            from apps.schools.celery_tasks import _run_with_tenant_context

            result = _run_with_tenant_context(
                school_id=school_id, runnable=sync_school_events
            )
            self.stdout.write(
                self.style.SUCCESS(f"calendar sync (school={school_id}): {result}")
            )
            return

        totals = _sync_calendar_events_all_tenants()
        self.stdout.write(
            self.style.SUCCESS(f"calendar sync (all tenants): {totals}")
        )
