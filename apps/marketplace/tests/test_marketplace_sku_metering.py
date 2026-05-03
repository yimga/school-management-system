"""SKU-wide metering registry closure — every monetizable category has an explicit contract."""

from __future__ import annotations

from django.test import TestCase

from apps.marketplace.marketplace_sku_registry import (
    MARKETPLACE_SKU_CONTRACTS,
    MarketplaceSkuContract,
    all_sku_keys,
    get_contract,
)


class MarketplaceSkuMeteringTests(TestCase):
    databases = {"default"}

    def test_all_categories_represented(self):
        keys = {c.sku_key for c in MARKETPLACE_SKU_CONTRACTS}
        self.assertGreaterEqual(len(keys), 8)
        required_substrings = (
            "mkt_app",
            "ai",
            "sms",
            "payment",
            "report",
            "workflow",
            "developer_api",
        )
        blob = " ".join(keys)
        for frag in required_substrings:
            self.assertIn(frag, blob)

    def test_each_contract_has_meter_or_subscription_semantics(self):
        for c in MARKETPLACE_SKU_CONTRACTS:
            self.assertIsInstance(c, MarketplaceSkuContract)
            self.assertTrue(c.sku_key)
            self.assertTrue(c.display_name)
            self.assertTrue(c.billing_model)

    def test_get_contract_roundtrip(self):
        self.assertIsNotNone(get_contract("mkt_app_subscription"))
        self.assertIsNone(get_contract("not_a_real_sku"))

    def test_sku_keys_unique(self):
        ks = list(all_sku_keys())
        self.assertEqual(len(ks), len(set(ks)))
