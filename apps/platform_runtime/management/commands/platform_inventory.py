"""
§7 Marketplace seed targets: output catalog counts for MARKETPLACE_SEED_TARGETS.md.
Run: python manage.py platform_inventory
      python manage.py platform_inventory --format json  # for scripted §2 refresh
"""

import json

from django.core.management.base import BaseCommand

from apps.platform_runtime.catalog_counts import get_platform_catalog_counts


class Command(BaseCommand):
    help = "Output platform/marketplace catalog counts for MARKETPLACE_SEED_TARGETS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            default="text",
            choices=["text", "json"],
            help="Output format: text (human) or json (for scripted MARKETPLACE_SEED_TARGETS §2 refresh).",
        )

    def handle(self, *args, **options):
        counts = get_platform_catalog_counts()

        if options.get("format") == "json":
            self.stdout.write(json.dumps(counts, indent=2))
            return

        self.stdout.write("Catalog counts (for MARKETPLACE_SEED_TARGETS.md):")
        self.stdout.write(
            f"  First-party apps (distinct package_id): {counts['first_party_apps']}"
        )
        self.stdout.write(
            f"  Blueprint packs (catalog):              {counts['blueprint_packs']}"
        )
        self.stdout.write(
            f"  Workflow packs (catalog):               {counts['workflow_packs']}"
        )
        self.stdout.write(
            f"  Dashboard packs (catalog):              {counts['dashboard_packs']}"
        )
        self.stdout.write(
            f"  Policy bundles (catalog):              {counts['policy_bundles']}"
        )
        self.stdout.write(
            "  Installed (active): blueprint={}, workflow={}, dashboard={}, policy={}, theme={}".format(
                counts["installed_blueprint"],
                counts["installed_workflow"],
                counts["installed_dashboard"],
                counts["installed_policy"],
                counts["installed_theme"],
            )
        )
