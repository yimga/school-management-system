"""
Idempotent seed for CalendarSystemRegistry rows matching RegionConfig.calendar_system codes.

Run after deploy or in CI migrate hooks: ``python manage.py ensure_calendar_system_registry``

The canonical row set now lives in ``apps.registries.services`` (single source of
truth shared with ``ensure_registry_baseline`` and the launch-page self-heal); this
command is a thin operator entry point over that helper.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.registries.models import CalendarSystemRegistry
from apps.registries.services import (
    CALENDAR_SYSTEM_SEED_DEFAULTS,
    ensure_calendar_system_registry_seed,
)


class Command(BaseCommand):
    help = "Ensure CalendarSystemRegistry has active rows for all RegionConfig calendar_system values."

    def handle(self, *args, **options):
        before = CalendarSystemRegistry.objects.count()
        ensure_calendar_system_registry_seed()
        after = CalendarSystemRegistry.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"CalendarSystemRegistry: {after - before} created, "
                f"{len(CALENDAR_SYSTEM_SEED_DEFAULTS)} codes ensured "
                f"({after} active total)."
            )
        )
