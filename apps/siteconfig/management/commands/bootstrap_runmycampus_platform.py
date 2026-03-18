"""
Umbrella bootstrap for RunMyCampus platform: one command to bring a fresh
environment to a living state (registries, blueprint packs, policy bundles,
workflow/dashboard packs, marketplace apps, portal content, compliance baseline).
Idempotent. Delegates to bootstrap_platform_catalog --all.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Bootstrap RunMyCampus platform end-to-end: seed registries, blueprint/policy packs, "
        "workflow/dashboard packs, marketplace apps, portal FAQs/KB, finance defaults, compliance baseline. "
        "Idempotent. Use for first-time setup or to ensure Manager surfaces are populated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pass --dry-run to seed commands that support it.",
        )

    def handle(self, *args, **options):
        extra = ["--all"]
        if options["dry_run"]:
            extra.append("--dry-run")

        self.stdout.write(
            "Bootstrapping RunMyCampus platform (full catalog + registries + portal + compliance)…"
        )
        call_command(
            "bootstrap_platform_catalog", *extra, verbosity=options["verbosity"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                "RunMyCampus platform bootstrap complete. Blueprint marketplace, app catalog, "
                "workflow/dashboard packs, registries, and portal content are seeded."
            )
        )
