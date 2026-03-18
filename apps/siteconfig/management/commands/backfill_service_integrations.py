"""Backfill ServiceIntegration from legacy Integration rows."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.schools.models import School
from apps.siteconfig.integration_registry import (
    backfill_service_integrations_from_legacy,
)


class Command(BaseCommand):
    help = "Backfill ServiceIntegration records from legacy Integration rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", type=str, default="", help="Optional school slug filter"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Preview changes without writing"
        )

    def handle(self, *args, **options):
        slug = (options.get("school") or "").strip()
        dry_run = bool(options.get("dry_run"))
        school = None
        if slug:
            school = School.objects.filter(slug=slug).first()
            if not school:
                self.stdout.write(self.style.ERROR(f"School not found: {slug}"))
                return

        results = backfill_service_integrations_from_legacy(
            school=school, dry_run=dry_run
        )
        created = sum(1 for r in results if r.get("action") == "created")
        updated = sum(1 for r in results if r.get("action") == "updated")
        would = sum(1 for r in results if r.get("action") == "would_upsert")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run: would_upsert={would}"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backfill complete: created={created} updated={updated}"
                )
            )
