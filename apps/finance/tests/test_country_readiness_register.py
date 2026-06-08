"""Tests for the Country Readiness Register — the world-wide readiness truth table."""

from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from apps.finance import country_readiness_register as reg


class CountryReadinessRegisterTests(unittest.TestCase):
    def setUp(self):
        # The register memoizes with lru_cache; clear so per-test PSP patches take.
        reg.all_assessments.cache_clear()
        reg._psp_rows.cache_clear()
        reg._payment_profiles.cache_clear()

    def test_every_payment_profile_country_is_assessable(self):
        profiles = reg._payment_profiles()
        self.assertGreaterEqual(len(profiles), 200, "expected the full-world payment profile SOT")
        a = reg.all_assessments()
        self.assertEqual(len(a), len(profiles), "every country must resolve to a readiness row")
        for cc, row in a.items():
            self.assertIn(row["overall_tier"], reg.TIER_ORDER, f"{cc} has an unknown tier")
            self.assertTrue(row["currency"], f"{cc} missing currency")
            self.assertTrue(row["tenant_action"], f"{cc} missing tenant action")
            self.assertTrue(row["platform_action"], f"{cc} missing platform action")

    def test_unknown_country_returns_none(self):
        self.assertIsNone(reg.assess_country("ZZ"))
        self.assertIsNone(reg.assess_country(""))

    def test_cameroon_leads_with_mtn_momo(self):
        cm = reg.assess_country("CM")
        self.assertEqual(cm["currency"], "XAF")
        self.assertIn("MTN_MOMO", cm["primary_rails"])
        # No rail is live today → config-blocked, blocked on the MoMo adapter.
        self.assertEqual(cm["overall_tier"], reg.TIER_ADAPTER_IN_PROGRESS)
        self.assertEqual(cm["blocking_psp"]["slug"], "mtn_momo")

    def test_nothing_is_config_only_until_an_adapter_is_live(self):
        """The honest invariant: with zero live PSPs, no country is fully config-only."""
        s = reg.summary()
        if s["live_rail_count"] == 0:
            self.assertEqual(s["by_tier"].get(reg.TIER_CONFIG_ONLY, 0), 0)

    def test_promoting_an_adapter_to_live_flips_its_countries_green(self):
        """Simulate MTN MoMo going live → XAF MoMo-led countries become config-only.
        This proves the config-scales-to-all-countries thesis mechanically."""
        live_rows = [
            dataclasses.replace(p, adapter_status="live") if p.psp_slug == "mtn_momo" else p
            for p in reg._psp_rows()
        ]

        reg.all_assessments.cache_clear()
        with mock.patch.object(reg, "_psp_rows", lambda: tuple(live_rows)):
            cm = reg.assess_country("CM")
            self.assertEqual(cm["payment_tier"], reg.TIER_CONFIG_ONLY)
            self.assertIn("credentials", cm["tenant_action"].lower())

    def test_summary_shape(self):
        s = reg.summary()
        for key in (
            "total_countries", "defined_corridors", "placeholder_corridors", "by_tier",
            "by_data_state", "by_blocking_psp", "by_locale", "by_risk_tier",
            "live_rail_count", "tier_order",
        ):
            self.assertIn(key, s)
        self.assertEqual(sum(s["by_tier"].values()), s["total_countries"])
        self.assertEqual(s["defined_corridors"] + s["placeholder_corridors"], s["total_countries"])

    # --- Aggressive-gap-analysis hardening (the placeholder-honesty + footgun layer) ---

    def test_placeholder_corridors_are_flagged_not_credited(self):
        """The headline-honesty fix: stub corridors (fake USD currency) must report as
        corridor_undefined, NOT be silently credited as adapter_in_progress."""
        s = reg.summary()
        # Most of the world is still placeholder data — that must be visible, not hidden.
        self.assertGreater(s["placeholder_corridors"], s["defined_corridors"])
        # China is the canonical stub (currency USD, "SFDP Phase 2 stub" note).
        cn = reg.assess_country("CN")
        self.assertEqual(cn["data_state"], "placeholder")
        self.assertEqual(cn["overall_tier"], reg.TIER_CORRIDOR_UNDEFINED)

    def test_defined_corridor_is_assessed_for_real(self):
        """A researched corridor (Cameroon) keeps a real readiness verdict, not corridor_undefined."""
        cm = reg.assess_country("CM")
        self.assertEqual(cm["data_state"], "defined")
        self.assertNotEqual(cm["overall_tier"], reg.TIER_CORRIDOR_UNDEFINED)

    def test_leverage_is_computed_over_defined_corridors_only(self):
        """Honest leverage: the top blocking PSP must not be inflated by stub countries
        sharing a fake USD currency (the old 'one PSP covers 240' artifact)."""
        s = reg.summary()
        # No single adapter can 'unblock' more than the number of defined corridors.
        for count in s["by_blocking_psp"].values():
            self.assertLessEqual(count, s["defined_corridors"])

    def test_languages_unioned_across_multiple_profiles(self):
        """Cameroon carries an anglophone AND a francophone profile; both languages must survive."""
        cm = reg.assess_country("CM")
        self.assertIn("en", cm["languages"])
        self.assertIn("fr", cm["languages"])

    def test_zero_decimal_currency_flagged(self):
        """XAF is zero-decimal — the register must flag it so a tenant doesn't charge 100×."""
        cm = reg.assess_country("CM")
        self.assertEqual(cm["currency"], "XAF")
        self.assertEqual(cm["minor_units"], 0)
        self.assertTrue(cm["zero_decimal"])
        # A 2-decimal currency must NOT be flagged.
        us = reg.assess_country("US")
        self.assertFalse(us["zero_decimal"])

    def test_every_rail_in_the_data_is_classified(self):
        """Coverage guard: no primary/backup rail token may fall through to silent platform_build."""
        self.assertEqual(reg.unclassified_rails(), {})


if __name__ == "__main__":
    unittest.main()
