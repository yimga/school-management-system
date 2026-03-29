"""
Seed or update ``Plan`` rows from ``billing_sku_registry`` BR-10 tier bundles.

Idempotent: uses ``update_or_create`` on slug ``br10-<tier>``. Does not delete other plans.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.siteconfig.billing_sku_registry import (
    BR10_TIER_CORE,
    BR10_TIER_INTELLIGENCE,
    BR10_TIER_INTEROP,
    ordered_features_for_br10_tier,
)
from apps.siteconfig.models_platform_catalog import Plan

_DEFAULT_TIER_SPECS: tuple[tuple[str, str, str], ...] = (
    (BR10_TIER_CORE, "br10-core", "BR-10 Core"),
    (BR10_TIER_INTEROP, "br10-interop", "BR-10 Interop"),
    (BR10_TIER_INTELLIGENCE, "br10-intelligence", "BR-10 Intelligence"),
)


class Command(BaseCommand):
    help = (
        "Upsert Plan rows for BR-10 tiers (included_features from billing_sku_registry)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tier",
            action="append",
            dest="tiers",
            choices=[BR10_TIER_CORE, BR10_TIER_INTEROP, BR10_TIER_INTELLIGENCE],
            help="Limit to one or more tiers (default: all). Repeatable.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print actions without writing the database.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        wanted = options.get("tiers") or None
        specs = _DEFAULT_TIER_SPECS
        if wanted:
            wset = {str(x).strip().lower() for x in wanted}
            specs = tuple(s for s in specs if s[0] in wset)

        for tier_key, slug, name in specs:
            features = ordered_features_for_br10_tier(tier_key)
            if dry_run:
                self.stdout.write(
                    f"[dry-run] {slug}: {name} -> included_features={features!r}"
                )
                continue
            _obj, created = Plan.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "included_features": features,
                    "is_active": True,
                },
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"{verb} Plan slug={slug!r} ({len(features)} features)")
            )
