"""
Management command — bulk-seed SubdivisionRegistry from pycountry ISO 3166-2.

Idempotent: uses ``update_or_create`` on ``(country, code)`` like
``sync_subdivisions_from_legacy_provinces``. After seeding, updates
``docs/generated/country_governance_matrix.json`` (and per-country shards)
so ``deep_layers.subdivisions_seeded`` is true for countries with >=1 row.

Usage::

    python manage.py seed_iso3166_subdivisions [--dry-run] [--quiet]
    python manage.py seed_iso3166_subdivisions --country US --country CA
    python manage.py seed_iso3166_subdivisions --skip-matrix
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.registries.services import (
    seed_iso3166_subdivisions,
    update_governance_matrix_subdivision_flags,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Bulk-seed SubdivisionRegistry from pycountry ISO 3166-2 subdivisions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be inserted/updated without writing.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress per-country output; only print summary.",
        )
        parser.add_argument(
            "--country",
            action="append",
            default=None,
            dest="countries",
            metavar="ALPHA2",
            help="Limit seeding to one or more ISO alpha-2 country codes.",
        )
        parser.add_argument(
            "--skip-matrix",
            action="store_true",
            help="Skip updating country_governance_matrix subdivision flags.",
        )

    def handle(self, *args, **opts):
        dry_run: bool = bool(opts.get("dry_run"))
        quiet: bool = bool(opts.get("quiet"))
        countries: list[str] | None = opts.get("countries")
        skip_matrix: bool = bool(opts.get("skip_matrix"))

        if dry_run:
            result = seed_iso3166_subdivisions(dry_run=True, country_codes=countries)
        else:
            with transaction.atomic():
                result = seed_iso3166_subdivisions(country_codes=countries)
                matrix_flagged = 0
                if not skip_matrix:
                    matrix_flagged = update_governance_matrix_subdivision_flags()

        if not quiet:
            for code in result.countries_with_subdivisions:
                self.stdout.write(f"  subdivisions: {code}")

        summary = (
            f"countries={result.countries_processed} "
            f"created={result.subdivisions_created} "
            f"updated={result.subdivisions_updated} "
            f"with_subdivisions={len(result.countries_with_subdivisions)}"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN — {summary}"))
            return

        if not skip_matrix:
            self.stdout.write(
                self.style.SUCCESS(
                    f"ISO 3166-2 subdivisions seeded ({summary}); "
                    f"matrix flags updated for {matrix_flagged} countries."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"ISO 3166-2 subdivisions seeded ({summary})."))
