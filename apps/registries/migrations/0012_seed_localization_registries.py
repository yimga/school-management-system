"""Durable seed of the localization reference registries.

The TimeZone / Locale / InstitutionType / CalendarSystem registries had NO
deploy-time seeder — they were written only by test fixtures — so a freshly
migrated database (DR restore, new region, staging rebuild, preview env) had
those four tables EMPTY. Every school whose timezone / locale / school_type /
calendar_system was set then rendered a permanent "yellow triangle" on the
Launch/Setup registry-alignment card, platform-wide.

This mirrors ``0008_seed_grade_scale_registry`` / ``0011_seed_currency_country``:
it reads the SAME single-source-of-truth constants the service uses (no drifting
copy) and writes via the *historical* models. Idempotent (``update_or_create``
keyed on ``code``) and safe to re-run; reverse is a no-op because reference data
is never torn down on rollback.
"""

from __future__ import annotations

from datetime import datetime

import pytz
from django.db import migrations


def seed_localization_registries(apps, schema_editor):
    TimeZoneRegistry = apps.get_model("registries", "TimeZoneRegistry")
    LocaleRegistry = apps.get_model("registries", "LocaleRegistry")
    InstitutionTypeRegistry = apps.get_model("registries", "InstitutionTypeRegistry")
    CalendarSystemRegistry = apps.get_model("registries", "CalendarSystemRegistry")

    # Pure-data constants (no live-model references) — safe to import at run time.
    from apps.registries.services import (
        CALENDAR_SYSTEM_SEED_DEFAULTS,
        INSTITUTION_TYPE_SEED_DEFAULTS,
        LOCALE_SEED_DEFAULTS,
        _TIMEZONE_SPECIAL_NAMES,
    )

    reference = datetime(2000, 1, 1, 12, 0, 0)  # deterministic standard-time offset
    for tz_name in pytz.all_timezones:
        offset_fmt = ""
        try:
            raw = pytz.timezone(tz_name).localize(reference).strftime("%z")
            if len(raw) == 5:
                offset_fmt = f"{raw[:3]}:{raw[3:]}"
        except Exception:  # noqa: BLE001 — offset is informational
            offset_fmt = ""
        display = _TIMEZONE_SPECIAL_NAMES.get(tz_name) or tz_name.replace("_", " ")
        TimeZoneRegistry.objects.update_or_create(
            code=tz_name,
            defaults={"name": display, "utc_offset": offset_fmt, "is_active": True},
        )

    for row in LOCALE_SEED_DEFAULTS:
        LocaleRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "is_rtl": bool(row.get("is_rtl")),
                "is_active": True,
            },
        )

    for row in INSTITUTION_TYPE_SEED_DEFAULTS:
        InstitutionTypeRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "sort_order": row.get("sort_order", 0),
                "is_active": True,
            },
        )

    for row in CALENDAR_SYSTEM_SEED_DEFAULTS:
        CalendarSystemRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "metadata": row.get("metadata", {}),
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("registries", "0011_seed_currency_country_registries"),
    ]

    operations = [
        migrations.RunPython(seed_localization_registries, migrations.RunPython.noop),
    ]
