"""
Align all marketplace catalog app slugs with PackageVersion payloads.

Idempotent: update_or_create by (package_id, version). Run after seed_marketplace_apps:

  python manage.py seed_marketplace_apps
  python manage.py seed_marketplace_catalog_packages

Verifier: python scripts/verify_marketplace_package_payload_parity.py
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from apps.marketplace.management.commands.seed_marketplace_apps import FIRST_PARTY_APPS
from apps.marketplace.marketplace_package_payloads import catalog_app_package_rows
from apps.packages.models import PackageVersion

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Seed PackageVersion rows for all marketplace catalog apps (73 slugs) "
        "so activate applies real pack content."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log rows without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        rows = catalog_app_package_rows(FIRST_PARTY_APPS)
        ensured = 0
        for row in rows:
            pid = row["package_id"]
            ver = row["version"]
            if dry_run:
                sections = list((row.get("payload_sections") or {}).keys())
                self.stdout.write(f"Would upsert {pid}@{ver} sections={sections}")
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
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY-RUN] Would ensure {ensured} marketplace catalog package versions."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Marketplace catalog package versions: {ensured} ensured "
                    f"({len(FIRST_PARTY_APPS)} catalog apps)."
                )
            )
