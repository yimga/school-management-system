"""
Phase Global: Seed global registry from open data (regions, country profiles, brand registry).
Orchestrates seed_global_regions, seed_country_profiles, and seed_global_brand_registry
so one command hydrates the global catalog.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed global data: regions + country education profiles (Phase Global)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-profiles",
            action="store_true",
            help="Also seed baseline education profiles per country (default: True).",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing RegionConfig rows with latest catalog data.",
        )
        parser.add_argument(
            "--skip-profiles",
            action="store_true",
            help="Only seed regions; do not run seed_country_profiles.",
        )
        parser.add_argument(
            "--skip-brand-registry",
            action="store_true",
            help="Do not run seed_global_brand_registry.",
        )
        parser.add_argument(
            "--skip-unesco",
            action="store_true",
            help="Pass through to seed_global_brand_registry to skip UNESCO calls.",
        )

    def handle(self, *args, **options):
        with_profiles = options.get("with_profiles", True) and not options.get(
            "skip_profiles"
        )
        update_existing = options.get("update_existing", False)

        self.stdout.write("Seeding global regions...")
        call_command(
            "seed_global_regions",
            with_profiles=with_profiles,
            update_existing=update_existing,
        )

        if not options.get("skip_profiles"):
            self.stdout.write("Seeding country education profiles...")
            call_command("seed_country_profiles")

        if not options.get("skip_brand_registry"):
            self.stdout.write("Seeding global brand registry...")
            call_command(
                "seed_global_brand_registry",
                skip_unesco=options.get("skip_unesco", False),
            )

        self.stdout.write(self.style.SUCCESS("seed_global_data complete."))
