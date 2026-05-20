"""
Persist the worldwide city catalog for header weather + feature control.

Requires pycountry + geonamescache at seed time. After this runs once per
environment, workers can serve the full catalog from the database even if
optional Python deps are temporarily unavailable.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.models import WeatherLocation


class Command(BaseCommand):
    help = (
        "Seed RegionConfig + WeatherLocation from the global geonames catalog "
        "(all ISO countries, ~23k cities)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-sync even when persisted rows already exist.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not GlobalGeoCatalog.has_live_catalog():
            self.stderr.write(
                self.style.ERROR(
                    "Live catalog unavailable. Install requirements: "
                    "pycountry geonamescache (see requirements.txt)."
                )
            )
            return

        if GlobalGeoCatalog.has_persisted_catalog() and not options.get("force"):
            count = WeatherLocation.objects.filter(
                catalog_source_id__isnull=False
            ).count()
            self.stdout.write(
                self.style.WARNING(
                    f"Persisted catalog already present ({count} cities). "
                    "Pass --force to re-sync."
                )
            )
            return

        self.stdout.write("Syncing global countries and cities into the database...")
        stats = WeatherLocation.sync_from_global_catalog()
        if stats.get("skipped"):
            self.stderr.write(self.style.ERROR("Sync skipped — live catalog missing."))
            return

        total = WeatherLocation.objects.filter(catalog_source_id__isnull=False).count()
        countries = WeatherLocation.objects.filter(
            catalog_source_id__isnull=False
        ).values_list("region_id", flat=True).distinct().count()
        self.stdout.write(
            self.style.SUCCESS(
                "seed_global_weather_locations complete: "
                f"{countries} countries, {total} cities "
                f"(+{stats.get('cities_created', 0)} created, "
                f"{stats.get('cities_updated', 0)} updated)."
            )
        )
