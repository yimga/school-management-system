"""The two tenant config hubs must link to each other.

A school has two configuration front doors — the School Configuration Center
(platform_runtime) and the Portal Configure Hub (portal). They never referenced
each other, so a school admin who landed in one had no path to the other and
looked like they had seen "all" the settings. These lock a link in BOTH
directions.
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.platform_runtime.administration_catalog import TENANT_CONFIGURATION_SECTIONS
from apps.portal.views_configure import _build_catalog


class ConfigHubCrossLinkTests(SimpleTestCase):
    def test_config_center_links_to_portal_configure_hub(self):
        route_names = {s.get("route_name") for s in TENANT_CONFIGURATION_SECTIONS}
        self.assertIn(
            "portal_configure",
            route_names,
            "the School Configuration Center has no card for the Portal Configure Hub",
        )

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_portal_configure_hub_links_to_config_center(self):
        catalog = _build_catalog()
        labels = {e.label for cat in catalog for e in cat.entries}
        self.assertIn("School Configuration Center", labels)
        # And the link actually resolves on the tenant host (not a dead entry).
        entry = next(
            e for cat in catalog for e in cat.entries
            if e.label == "School Configuration Center"
        )
        self.assertTrue(entry.url, "the cross-link resolved to no URL")
