"""
Verify that RegionConfig covers all countries from the global catalog.

Part 1 / Part 4 item 4: Run seed_global_regions at deploy; add verify_region_coverage.
Reports missing regions and optional Province coverage. See docs/RUNMYCAMPUS_DEPLOYMENT.md.
"""
from django.core.management.base import BaseCommand
from django.db import DatabaseError, OperationalError, ProgrammingError

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.siteconfig.models import RegionConfig

# §2.4 Typed exceptions for optional Province coverage (broad_exception_audit)
_VERIFY_REGION_COVERAGE_PROVINCE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
    OperationalError,
    ProgrammingError,
)


class Command(BaseCommand):
    help = "Verify RegionConfig coverage against global country catalog (pycountry)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with non-zero if any country is missing.",
        )

    def handle(self, *args, **options):
        try:
            from apps.siteconfig.global_catalog import GlobalGeoCatalog
        except ImportError:
            self.stdout.write(self.style.ERROR("GlobalGeoCatalog unavailable."))
            return 1

        countries = GlobalGeoCatalog.list_countries()
        if not countries:
            self.stdout.write(
                self.style.WARNING(
                    "Global catalog returned no countries. Install pycountry (and optionally geonamescache)."
                )
            )
            return 2 if options.get("strict") else 0

        existing_codes = set(RegionConfig.objects.values_list("code", flat=True))
        missing = [c for c in countries if (c.get("code") or "").upper() not in existing_codes]
        covered = len(countries) - len(missing)

        self.stdout.write("RegionConfig coverage: %s / %s countries" % (covered, len(countries)))
        if missing:
            self.stdout.write(
                self.style.WARNING("Missing regions (%s): %s" % (len(missing), [m.get("code") for m in missing[:20]]))
            )
            if len(missing) > 20:
                self.stdout.write("  ... and %s more." % (len(missing) - 20))
            self.stdout.write("  Run: python manage.py seed_global_regions")
        else:
            self.stdout.write(self.style.SUCCESS("All catalog countries have a RegionConfig."))

        # Optional: Province coverage (informational)
        try:
            from apps.siteconfig.models import Province
            provinces = Province.objects.count()
            self.stdout.write("Provinces/States in catalog: %s (optional; seed per deployment)." % provinces)
        except _VERIFY_REGION_COVERAGE_PROVINCE_ERRORS as e:
            log_exception_with_context(
                "verify_region_coverage: optional Province count failed",
                school_id=None,
                extra={"command": "verify_region_coverage", "error": str(e)},
            )

        return 1 if (missing and options.get("strict")) else 0
