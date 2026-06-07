"""
§7 MARKETPLACE_SEED_TARGETS: seed PackageVersion so first-party apps (distinct package_id) reach 25+.

Idempotent: update_or_create by (package_id, version). Minimum 25 distinct package_id per
docs/MARKETPLACE_SEED_TARGETS.md §1; this command seeds 27 for headroom.

Run: python manage.py seed_first_party_apps
      python manage.py seed_first_party_apps --dry-run  # show what would be ensured
"""

import logging

from django.core.management.base import BaseCommand

from apps.packages.first_party_package_payloads import (
    FIRST_PARTY_APP_DEFINITIONS,
    first_party_package_rows,
)
from apps.packages.models import PackageVersion

logger = logging.getLogger(__name__)

# Back-compat alias for scripts/tests that import FIRST_PARTY_APPS from this module.
FIRST_PARTY_APPS = FIRST_PARTY_APP_DEFINITIONS


class Command(BaseCommand):
    help = "Seed PackageVersion so first-party apps (distinct package_id) reach 25+ for MARKETPLACE_SEED_TARGETS §7."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log what would be created/updated without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        rows = first_party_package_rows(FIRST_PARTY_APP_DEFINITIONS)
        ensured = 0
        for row in rows:
            pid = row["package_id"]
            ver = row["version"]
            if dry_run:
                sections = list((row.get("payload_sections") or {}).keys())
                logger.debug(
                    "Would ensure package_id=%s version=%s sections=%s",
                    pid,
                    ver,
                    sections,
                )
                ensured += 1
                continue
            PackageVersion.objects.update_or_create(
                package_id=pid,
                version=ver,
                defaults={
                    "payload_sections": dict(row.get("payload_sections") or {}),
                    "changelog_summary": row.get("changelog_summary") or "",
                    "compatibility": dict(row.get("compatibility") or {}),
                    "dependencies": [],
                },
            )
            ensured += 1
        distinct = len(FIRST_PARTY_APP_DEFINITIONS)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY-RUN] Would ensure {ensured} first-party app versions "
                    f"(distinct package_id: {distinct})."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"First-party app versions: {ensured} ensured (distinct package_id: {distinct})."
                )
            )
        self.stdout.write(
            "Run: python manage.py platform_inventory --format json to verify first_party_apps count."
        )
