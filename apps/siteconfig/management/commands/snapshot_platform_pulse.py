"""snapshot_platform_pulse — daily capture of the 6 cockpit pulse cards.

Scheduled at 01:15 UTC via Celery beat ``cockpit-platform-pulse-snapshot-daily``.
Idempotent: re-running on the same UTC date is a no-op (the unique constraint
on ``(snapshot_date, metric_key)`` is honored via ``update_or_create``).

Manual usage:
    python manage.py snapshot_platform_pulse
    python manage.py snapshot_platform_pulse --date 2026-05-20  # backfill one day
    python manage.py snapshot_platform_pulse --dry-run

Posture: aggregate counts only — never tenant slugs or PII.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls, datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Capture today's platform-pulse KPI values into the snapshot table."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--date",
            type=str,
            default="",
            help="Override snapshot date (YYYY-MM-DD UTC). Defaults to today.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Resolve and print values without writing rows.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        from apps.siteconfig.cockpit_platform_pulse_service import _iter_pulse_resolvers
        from apps.siteconfig.models_pulse_snapshot import PlatformPulseSnapshot

        if opts["date"]:
            try:
                snapshot_date = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError(f"Invalid --date: {exc}") from exc
        else:
            snapshot_date = timezone.now().date()

        written = 0
        skipped = 0
        for slot, resolver in _iter_pulse_resolvers():
            try:
                card = resolver()
            except Exception:
                logger.warning("snapshot_platform_pulse: %s resolver crashed", slot, exc_info=True)
                card = None
            if not card:
                self.stdout.write(self.style.WARNING(f"  skip {slot}: resolver returned None"))
                skipped += 1
                continue

            raw_value = int(card.get("raw_value", 0))
            display_value = str(card.get("value", ""))[:64]

            if opts["dry_run"]:
                self.stdout.write(
                    f"  would write {slot}: raw={raw_value} display={display_value!r}"
                )
                written += 1
                continue

            PlatformPulseSnapshot.objects.update_or_create(
                snapshot_date=snapshot_date,
                metric_key=slot,
                defaults={
                    "raw_value": raw_value,
                    "display_value": display_value,
                },
            )
            written += 1

        verb = "would write" if opts["dry_run"] else "wrote"
        self.stdout.write(self.style.SUCCESS(
            f"snapshot_platform_pulse[{snapshot_date}]: {verb} {written}, skipped {skipped}"
        ))
