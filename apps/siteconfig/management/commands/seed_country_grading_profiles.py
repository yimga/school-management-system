from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.country_grading_seed import (
    COUNTRY_GRADING_SEED_SOURCE,
    invalid_scale_types,
    seed_country_grading_profiles,
)


class Command(BaseCommand):
    help = (
        "Seed / re-seed platform CountryGradingProfile rows (country -> default "
        "grading scale). Idempotent; never reactivates an operator-disabled row."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help=(
                "Validate the seed's scale_type values against the live "
                "GradingScale.ScaleType choices and exit without writing."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        bad = invalid_scale_types()
        if bad:
            self.stderr.write(
                self.style.ERROR(
                    "CountryGradingProfile seed references unknown scale types: "
                    + ", ".join(bad)
                )
            )
            return
        if options.get("check"):
            self.stdout.write(
                self.style.SUCCESS("CountryGradingProfile seed scale types are valid.")
            )
            return
        summary = seed_country_grading_profiles()
        self.stdout.write(
            self.style.SUCCESS(
                "CountryGradingProfile seed complete "
                f"(created={summary.get('created', 0)}, "
                f"updated={summary.get('updated', 0)}, "
                f"rows={summary.get('total_rows', 0)}). "
                f"Source: {COUNTRY_GRADING_SEED_SOURCE}"
            )
        )
