# -*- coding: utf-8 -*-
"""
Seed operational-only PlatformOperatorSuperDashboardLink rows.

Configuration-tier destinations (grading matrices, OAuth, tax) live under
/configuration/ and /admin/ — not on the /super/ command center home.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.models import PlatformOperatorSuperDashboardLink
from apps.schools.dashboard_topology_registry import (
    DEFAULT_OPERATIONAL_SUPER_DASHBOARD_LINKS,
    SURFACE_TIER_CONFIGURATION,
    SURFACE_TIER_OPERATIONAL,
    href_is_configuration_tier,
)


class Command(BaseCommand):
    help = "Seed dual-dashboard operational quick links for the platform super dashboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune-config",
            action="store_true",
            help="Delete or re-tier curated links that point at configuration surfaces.",
        )

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for slug, label, href, sort_order in DEFAULT_OPERATIONAL_SUPER_DASHBOARD_LINKS:
            if href_is_configuration_tier(href):
                self.stderr.write(self.style.ERROR(f"Refusing config href for seed: {href}"))
                continue
            _obj, was_created = PlatformOperatorSuperDashboardLink.objects.update_or_create(
                slug=slug,
                defaults={
                    "label": label,
                    "href": href,
                    "sort_order": sort_order,
                    "category": "super_dashboard",
                    "surface_tier": SURFACE_TIER_OPERATIONAL,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        pruned = 0
        if options.get("prune_config"):
            for row in PlatformOperatorSuperDashboardLink.objects.all().iterator():
                if href_is_configuration_tier(row.href):
                    row.surface_tier = SURFACE_TIER_CONFIGURATION
                    row.save(update_fields=["surface_tier", "updated_at"])
                    pruned += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_dashboard_topology_links: created={created} updated={updated} "
                f"re_tiered_config={pruned}"
            )
        )
