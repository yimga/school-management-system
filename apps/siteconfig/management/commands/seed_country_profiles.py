from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.education_profile_engine import (
    ensure_country_profile,
    ensure_region_for_country,
    normalize_sub_system,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog


class Command(BaseCommand):
    help = "Seed education system profiles for global country packs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--country",
            default="",
            help="Optional ISO code (alpha-2 or alpha-3) to seed a single country.",
        )
        parser.add_argument(
            "--sub-system",
            default="ANY",
            help="ANY, EN, FR, or INT (default ANY).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        requested_country = GlobalGeoCatalog.normalize_country_code(options.get("country") or "")
        target_sub_system = normalize_sub_system(options.get("sub_system") or "ANY")

        countries: list[str]
        if requested_country:
            countries = [requested_country]
        else:
            countries = [str(item.get("code") or "") for item in GlobalGeoCatalog.list_countries() if item.get("code")]

        created_count = 0
        skipped_count = 0
        for country_code in countries:
            region = ensure_region_for_country(country_code)
            if region is None:
                skipped_count += 1
                continue
            profile = ensure_country_profile(region=region, sub_system=target_sub_system)
            if profile is None:
                skipped_count += 1
                continue
            if (profile.config or {}).get("generated"):
                created_count += 1
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Country profile seed complete. Countries={len(countries)} Generated/Resolved={created_count} Skipped={skipped_count}"
            )
        )
