from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.billing.country_profile_seed import (
    _catalog_country_rows,
    seed_country_billing_profiles,
)


class Command(BaseCommand):
    help = "Seed configurable per-country billing profiles for global (250-country) pricing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options.get("dry_run"):
            from django.apps import apps

            rows = _catalog_country_rows(apps.get_model)
            self.stdout.write(
                f"[dry-run] would upsert {len(rows)} country billing profiles."
            )
            return

        summary = seed_country_billing_profiles()
        self.stdout.write(
            self.style.SUCCESS(
                "Country billing profile seed complete "
                f"(profiles={summary['profiles']}, created={summary['created']}, "
                f"updated={summary['updated']}, fallback_countries={summary['fallback_countries']})."
            )
        )
