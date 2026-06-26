from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.country_multiplier_seed import (
    PPP_SEED_SOURCE,
    expand_seed_to_all_countries,
    seed_country_multipliers,
)


class Command(BaseCommand):
    help = "Seed platform CountryMultiplier PPP rows (curated markets + optional catalog backfill)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--country",
            action="append",
            default=[],
            help="ISO alpha-2/3 code; repeat for multiple countries. Default: all curated rows.",
        )
        parser.add_argument(
            "--all-catalog",
            action="store_true",
            help="After curated seed, backfill 1.0× Zone B for every catalog country missing a row.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        countries = [c for c in (options.get("country") or []) if c]
        if options.get("all_catalog"):
            summary = expand_seed_to_all_countries()
        else:
            summary = seed_country_multipliers(
                country_codes=countries or None,
            )
        self.stdout.write(
            self.style.SUCCESS(
                "CountryMultiplier seed complete "
                f"(created={summary.get('created', 0)}, "
                f"updated={summary.get('updated', 0)}, "
                f"backfilled={summary.get('backfilled_default', 0)}). "
                f"Source: {PPP_SEED_SOURCE}"
            )
        )
