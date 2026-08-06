"""School Configuration Center catalog wiring guards.

Audit findings on ``TENANT_CONFIGURATION_SECTIONS``:
  * the Roles / Permissions card pointed at the raw Django admin index
    (``tenant_admin:index``) instead of the RBAC management dashboard;
  * the Module Market surface (``siteconfig:module_market``) was orphaned — no
    card in the config center reached it.
"""

from django.test import SimpleTestCase
from django.urls import reverse

from apps.platform_runtime.administration_catalog import TENANT_CONFIGURATION_SECTIONS


class ConfigCenterCatalogWiringTests(SimpleTestCase):
    def _card(self, name):
        return next(
            (s for s in TENANT_CONFIGURATION_SECTIONS if s["name"] == name), None
        )

    def test_roles_card_targets_the_rbac_dashboard(self):
        card = self._card("Roles / Permissions")
        self.assertIsNotNone(card)
        self.assertEqual(card["route_name"], "accounts:rbac")
        # Must resolve on the tenant urlconf, else the config center disables it.
        self.assertTrue(reverse(card["route_name"], urlconf="config.tenant_urls"))

    def test_module_market_has_a_config_center_card(self):
        card = self._card("Modules")
        self.assertIsNotNone(
            card, "Module Market must have a config-center card (it was orphaned)"
        )
        self.assertEqual(card["route_name"], "siteconfig:module_market")
        self.assertTrue(reverse(card["route_name"], urlconf="config.tenant_urls"))

    def test_every_card_declares_a_permission_and_probe(self):
        for card in TENANT_CONFIGURATION_SECTIONS:
            self.assertTrue(card.get("route_name"), card)
            self.assertTrue(card.get("permission"), card)
            self.assertTrue(card.get("probe"), card)
