"""Seed deterministic proof data for five-pillar platform gates."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Seed marketplace catalog, analytics demo bundles, and search_index backfill "
        "for five-pillar / six-pillar proof runs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-marketplace",
            action="store_true",
            help="Skip marketplace app catalog seed.",
        )
        parser.add_argument(
            "--skip-search-backfill",
            action="store_true",
            help="Skip search_index backfill (slow on large DBs).",
        )

    def handle(self, *args, **options):
        if not options["skip_marketplace"]:
            call_command("seed_marketplace_apps", verbosity=0)
            call_command("seed_marketplace_scopes", verbosity=0)
            call_command("seed_capability_registry", verbosity=0)
            self.stdout.write(self.style.SUCCESS("marketplace catalog seeded"))

        for slug in (
            "marketing-demo",
            "platform-overview",
            "platform-meal-ops",
            "audit-tenant",
        ):
            call_command("seed_analytics_demo", slug, "--validate", verbosity=0)
        self.stdout.write(self.style.SUCCESS("analytics demo bundles validated"))

        if not options["skip_search_backfill"]:
            call_command("backfill_search_indexes", verbosity=0)
            self.stdout.write(self.style.SUCCESS("search_index backfill complete"))

        self.stdout.write(self.style.SUCCESS("FIVE_PILLAR_PROOF_SEED_OK"))
