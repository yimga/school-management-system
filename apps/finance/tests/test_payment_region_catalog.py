"""Canonical payment orchestration ISO2 catalog vs RegionPaymentProfile parity."""

from django.core.management import call_command
from django.test import TestCase

from apps.finance.payment_region_catalog import (
    CANONICAL_PAYMENT_ORCHESTRATION_ISO2,
    ensure_canonical_region_payment_profiles,
    iso2_codes_missing_payment_profiles,
)
from apps.finance.models import RegionPaymentProfile


class PaymentRegionCatalogTests(TestCase):
    def test_catalog_includes_seed_finance_primary_corridor(self):
        self.assertIn("CM", CANONICAL_PAYMENT_ORCHESTRATION_ISO2)

    def test_seed_finance_defaults_leaves_no_catalog_gap(self):
        call_command("seed_finance_defaults")
        self.assertEqual(iso2_codes_missing_payment_profiles(), [])
        for iso2 in CANONICAL_PAYMENT_ORCHESTRATION_ISO2:
            rp = RegionPaymentProfile.objects.get(country_code=iso2)
            self.assertNotEqual(rp.primary_rail_id, rp.backup_rail_id)

    def test_ensure_is_idempotent(self):
        ensure_canonical_region_payment_profiles()
        ensure_canonical_region_payment_profiles()
        self.assertEqual(iso2_codes_missing_payment_profiles(), [])
