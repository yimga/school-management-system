"""
Pass 14.B: upsert AppPermissionScope rows from apps.marketplace.scopes_catalog.

Idempotent — safe to re-run after every catalog edit. Run via deploy hook so
the DB-backed catalog and the code-backed catalog stay in lockstep.

  python manage.py seed_marketplace_scopes
  python manage.py seed_marketplace_scopes --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.marketplace.models import AppPermissionScope
from apps.marketplace.scopes_catalog import MARKETPLACE_SCOPES


class Command(BaseCommand):
    help = "Upsert AppPermissionScope rows from the code-backed MARKETPLACE_SCOPES catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        if dry_run:
            self.stdout.write("Dry run: no changes will be written.")

        created = 0
        updated = 0
        for code, entry in MARKETPLACE_SCOPES.items():
            domain = (entry.get("domain") or "").strip()[:64]
            access = (entry.get("access") or "read").strip()[:8]
            description = (entry.get("description") or "").strip()[:255]

            if dry_run:
                existing = AppPermissionScope.objects.filter(code=code).first()
                if existing is None:
                    self.stdout.write(f"  would create: {code}")
                    created += 1
                elif (
                    existing.domain != domain
                    or existing.access != access
                    or existing.description != description
                ):
                    self.stdout.write(f"  would update: {code}")
                    updated += 1
                continue

            _, was_created = AppPermissionScope.objects.update_or_create(
                code=code,
                defaults={
                    "domain": domain,
                    "access": access,
                    "description": description,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Marketplace scopes: {len(MARKETPLACE_SCOPES)} total "
                f"({created} created, {updated} updated)."
            )
        )
