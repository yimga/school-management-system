"""The two tenant config hubs must link to each other.

A school has two configuration front doors — the School Configuration Center
(platform_runtime) and the Portal Configure Hub (portal). They never referenced
each other, so a school admin who landed in one had no path to the other and
looked like they had seen "all" the settings. These lock a link in BOTH
directions.
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.platform_runtime.administration_catalog import TENANT_CONFIGURATION_SECTIONS
from apps.portal.views_configure import _build_catalog


class ConfigHubCrossLinkTests(SimpleTestCase):
    def test_config_center_has_a_portal_configure_card(self):
        route_names = {s.get("route_name") for s in TENANT_CONFIGURATION_SECTIONS}
        self.assertIn(
            "portal_configure",
            route_names,
            "the School Configuration Center has no card for the Portal Configure Hub",
        )

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_config_center_portal_card_resolves(self):
        # The card's route must actually reverse on the tenant host.
        self.assertTrue(reverse("portal_configure"))

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_portal_configure_hub_links_to_config_center(self):
        catalog = _build_catalog()
        labels = {e.label for cat in catalog for e in cat.entries}
        self.assertIn("School Configuration Center", labels)
        entry = next(
            e for cat in catalog for e in cat.entries
            if e.label == "School Configuration Center"
        )
        self.assertTrue(entry.url, "the cross-link resolved to no URL")

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_every_setup_advanced_link_resolves(self):
        # Walk ALL entries of the new "Setup & Advanced" category — a dead entry
        # (e.g. a wrong reverse name) is silently dropped, so assert each resolved.
        catalog = _build_catalog()
        setup_cat = next((c for c in _build_catalog() if c.slug == "setup"), None)
        self.assertIsNotNone(setup_cat, "the Setup & Advanced category is missing")
        for entry in setup_cat.entries:
            self.assertTrue(
                entry.url,
                f"Setup & Advanced entry '{entry.label}' resolved to no URL "
                "(dead cross-link — wrong reverse name?)",
            )
        # And all three intended cards are present.
        labels = {e.label for e in setup_cat.entries}
        self.assertEqual(
            labels,
            {"School Configuration Center", "Blueprints", "Import data"},
        )
