"""Seed + surface_tier filtering for dual-dashboard topology."""

from django.core.management import call_command
from django.test import TestCase

from apps.platform_runtime.models import PlatformOperatorSuperDashboardLink
from apps.schools.dashboard_topology_registry import (
    SURFACE_TIER_CONFIGURATION,
    SURFACE_TIER_OPERATIONAL,
    filter_operational_dashboard_links,
    href_is_configuration_tier,
)


class DashboardTopologySeedTests(TestCase):
    def test_seed_command_creates_operational_links(self):
        call_command("seed_dashboard_topology_links", verbosity=0)
        self.assertTrue(
            PlatformOperatorSuperDashboardLink.objects.filter(
                slug="command-center", surface_tier=SURFACE_TIER_OPERATIONAL
            ).exists()
        )

    def test_filter_drops_configuration_tier_rows(self):
        PlatformOperatorSuperDashboardLink.objects.create(
            slug="ops-queue",
            label="Queues",
            href="/super/command-center/",
            surface_tier=SURFACE_TIER_OPERATIONAL,
        )
        PlatformOperatorSuperDashboardLink.objects.create(
            slug="config-grading",
            label="Grading (config)",
            href="/super/grading/",
            surface_tier=SURFACE_TIER_CONFIGURATION,
        )
        rows = filter_operational_dashboard_links(
            PlatformOperatorSuperDashboardLink.objects.order_by("slug")
        )
        slugs = {r.slug for r in rows}
        self.assertIn("ops-queue", slugs)
        self.assertNotIn("config-grading", slugs)

    def test_href_is_configuration_tier_detects_admin(self):
        self.assertTrue(href_is_configuration_tier("/admin/"))
        self.assertTrue(href_is_configuration_tier("/configuration/domains/"))
        self.assertFalse(href_is_configuration_tier("/super/command-center/"))

    def test_prune_config_retiers_leaked_hrefs(self):
        PlatformOperatorSuperDashboardLink.objects.create(
            slug="leaked-admin",
            label="Admin",
            href="/admin/",
            surface_tier=SURFACE_TIER_OPERATIONAL,
        )
        call_command("seed_dashboard_topology_links", "--prune-config", verbosity=0)
        row = PlatformOperatorSuperDashboardLink.objects.get(slug="leaked-admin")
        self.assertEqual(row.surface_tier, SURFACE_TIER_CONFIGURATION)
