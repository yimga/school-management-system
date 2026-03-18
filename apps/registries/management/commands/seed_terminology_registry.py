"""
Platform bootstrap: Ensure official starter terminology/registry data (countries,
education levels, system types, currencies, document types, fee categories, grade scales).
Delegates to seed_platform_registries so the platform has a named terminology/registry seed.
Idempotent. Run: python manage.py seed_terminology_registry
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Seed terminology/registry data (countries, education levels, system types, etc.). "
        "Delegates to seed_platform_registries. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run seed_platform_registries with --dry-run if supported (no-op for this delegate).",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        if dry_run:
            self.stdout.write(
                "Dry run: would ensure terminology/registry baseline (seed_platform_registries)."
            )
            return
        call_command("seed_platform_registries", verbosity=options.get("verbosity", 1))
        self.stdout.write(self.style.SUCCESS("Terminology/registry data ensured."))
