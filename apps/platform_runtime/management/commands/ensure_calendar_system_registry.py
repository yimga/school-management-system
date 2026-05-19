"""
Idempotent seed for CalendarSystemRegistry rows matching RegionConfig.calendar_system codes.

Run after deploy or in CI migrate hooks: ``python manage.py ensure_calendar_system_registry``
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.registries.models import CalendarSystemRegistry

# Keys must match RegionConfig.CALENDAR_CHOICES values (setup_studio lookup).
_REGISTRY_ROWS: tuple[tuple[str, str, dict], ...] = (
    ("gregorian", "Gregorian (civil)", {"runtime_code": "gregorian"}),
    ("islamic", "Islamic (Hijri)", {"runtime_code": "hijri"}),
    ("buddhist", "Buddhist / Thai solar", {"runtime_code": "buddhist"}),
    ("hebrew", "Hebrew calendar", {"runtime_code": "hebrew"}),
)


class Command(BaseCommand):
    help = "Ensure CalendarSystemRegistry has active rows for all RegionConfig calendar_system values."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for code, name, metadata in _REGISTRY_ROWS:
            row, was_created = CalendarSystemRegistry.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "metadata": metadata,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                if row.name != name or not row.is_active:
                    row.name = name
                    row.is_active = True
                    row.metadata = {**(row.metadata or {}), **metadata}
                    row.save(update_fields=["name", "is_active", "metadata", "updated_at"])
                    updated += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"CalendarSystemRegistry: {created} created, {updated} updated, "
                f"{len(_REGISTRY_ROWS)} codes ensured."
            )
        )
