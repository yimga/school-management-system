"""Normalized regional corridors (global payments closure)."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from apps.finance.models import ComplianceProfile
from apps.finance.payment_fallback import corridor_bundle_for_invoice, select_fallback_chain
from apps.finance.regional_payment_profiles import (
    clear_profile_cache,
    get_normalized_regional_profile,
    get_regional_profile,
    list_supported_country_codes,
    normalize_regional_profile_row,
)


class GlobalPaymentProfilesTests(TestCase):
    CORRIDORS = ("CM", "GH", "NG", "KE", "US", "GB", "EU")

    def tearDown(self):
        clear_profile_cache()

    def test_each_country_profile_resolves_with_normalized_fields(self):
        for cc in self.CORRIDORS:
            raw = get_regional_profile(cc)
            self.assertIsNotNone(raw, msg=f"missing catalog row for {cc}")
            norm = get_normalized_regional_profile(cc)
            self.assertIsNotNone(norm)
            self.assertEqual(norm.get("country_code"), cc)
            self.assertTrue(norm.get("primary_rail"))
            self.assertTrue(norm.get("backup_rail"))
            self.assertIn("manual_fallback", norm)
            self.assertIn("reconciliation_required", norm)
            self.assertTrue(norm.get("operator_setup_steps"))
            self.assertEqual(norm.get("provider_setup_status"), "external_required")
            self.assertTrue(norm.get("tenant_setup_steps"))
            self.assertTrue(norm.get("operator_ready_label"))

    def test_corridor_bundle_enriched_from_normalized_profile(self):
        profile = ComplianceProfile.objects.create(
            name="Ghana corridor",
            country_code="GH",
            currency_code="GHS",
            is_active=True,
        )
        inv = SimpleNamespace(profile=profile)
        bundle = corridor_bundle_for_invoice(inv)
        self.assertEqual(bundle.get("country_code"), "GH")
        self.assertEqual(bundle.get("primary_rail"), "BANK")
        self.assertEqual(bundle.get("backup_rail"), "MTN_MOMO")
        self.assertTrue(bundle.get("reconciliation_required"))

    def test_normalize_row_derives_singular_rails_from_lists(self):
        raw = {
            "country_code": "ZZ",
            "primary_rails": ["A", "B"],
            "backup_rails": ["C"],
            "manual_receipt_allowed": True,
        }
        norm = normalize_regional_profile_row(raw)
        self.assertEqual(norm["primary_rail"], "A")
        self.assertEqual(norm["backup_rail"], "C")

    def test_fallback_chain_orders_primary_then_backup(self):
        chain = select_fallback_chain("NG")
        self.assertGreater(len(chain), 0)
        self.assertEqual(chain[0], "BANK")

    def test_us_and_eu_disallow_offline_receipt_capture(self):
        us = get_regional_profile("US")
        self.assertFalse(us.get("offline_receipt_allowed"))
        eu = get_regional_profile("EU")
        self.assertFalse(eu.get("offline_receipt_allowed"))

    def test_supported_country_codes_lists_catalog_keys(self):
        codes = list_supported_country_codes()
        for cc in self.CORRIDORS:
            self.assertIn(cc, codes)
