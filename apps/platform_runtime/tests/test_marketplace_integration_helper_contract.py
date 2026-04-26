"""Contracts: marketplace integration dict ↔ domain_ownership ↔ runtime helper (Batch 14+ discipline)."""

from unittest.mock import patch

from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_marketplace_integration_settings,
    get_platform_site_settings_record,
)
from apps.siteconfig.domain_ownership import EXACT_FIELD_OWNERS


class MarketplaceIntegrationHelperContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Persisted singleton required for facade key parity checks (isolated DBs).
        get_platform_site_settings_record(create=True)

    def test_facade_dict_keys_are_classified_marketplace_integrations(self):
        """Every key surfaced by ``get_marketplace_integration_settings`` must map in domain_ownership."""
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        for key in site.get_marketplace_integration_settings().keys():
            self.assertEqual(
                EXACT_FIELD_OWNERS.get(key),
                "marketplace_integrations",
                msg=f"Add {key!r} to EXACT_FIELD_OWNERS or stop exposing it in the integration dict",
            )

    def test_effective_helper_matches_facade_key_set_when_site_unresolved(self):
        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings",
            return_value=None,
        ):
            got = get_effective_marketplace_integration_settings()
        site = get_platform_site_settings_record(create=False)
        self.assertIsNotNone(site)
        self.assertEqual(
            set(got.keys()),
            set(site.get_marketplace_integration_settings().keys()),
        )

    def test_platform_sitesettings_singleton_create_is_stable(self):
        """Singleton row used for integration key parity must persist across calls."""
        a = get_platform_site_settings_record(create=True)
        b = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(a.pk)
        self.assertEqual(a.pk, b.pk)
