"""Regional corridor metadata and payment fallback helpers."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from apps.finance.models import ComplianceProfile
from apps.finance.payment_fallback import corridor_bundle_for_invoice, select_fallback_chain
from apps.finance.regional_payment_profiles import (
    clear_profile_cache,
    get_regional_profile,
)


class RegionalPaymentProfilesTests(TestCase):
    def tearDown(self):
        clear_profile_cache()

    def test_cameroon_profile_loads(self):
        p = get_regional_profile("CM")
        self.assertIsNotNone(p)
        self.assertEqual(p.get("currency"), "XAF")
        self.assertIn("MTN_MOMO", p.get("primary_rails", []))

    def test_fallback_chain_orders_primary_then_backup(self):
        chain = select_fallback_chain("NG")
        self.assertGreater(len(chain), 0)
        self.assertEqual(chain[0], "BANK")

    def test_us_and_eu_profiles(self):
        us = get_regional_profile("US")
        self.assertEqual(us.get("currency"), "USD")
        self.assertFalse(us.get("offline_receipt_allowed"))
        eu = get_regional_profile("EU")
        self.assertEqual(eu.get("currency"), "EUR")
        chain_us = select_fallback_chain("US")
        self.assertIn("CARD", chain_us)

    def test_corridor_bundle_from_invoice(self):
        profile = ComplianceProfile.objects.create(
            name="Test Corridor",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        inv = SimpleNamespace(profile=profile)
        bundle = corridor_bundle_for_invoice(inv)
        self.assertEqual(bundle.get("country_code"), "CM")
        self.assertEqual(bundle.get("primary_method"), "MTN_MOMO")
        self.assertTrue(bundle.get("offline_receipt_allowed"))
