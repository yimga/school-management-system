"""Tests for the indicative published pricing tiers SOT."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.marketing_pricing_tiers import pricing_tiers


class PricingTiersTests(SimpleTestCase):
    def test_three_tiers(self):
        tiers = pricing_tiers()
        self.assertEqual(len(tiers), 3)
        self.assertEqual([t["key"] for t in tiers], ["starter", "growth", "enterprise"])

    def test_every_tier_is_indicative(self):
        for t in pricing_tiers():
            self.assertTrue(t["indicative"], f"{t['key']} must be flagged indicative")

    def test_non_empty_fields(self):
        for t in pricing_tiers():
            self.assertTrue(t["name"])
            self.assertTrue(t["who_for"])
            self.assertTrue(t["included"])
            self.assertTrue(t["cta_label"])
            self.assertTrue(t["cta_route"])
            self.assertTrue(t["price_note"])

    def test_figures_derived_from_calculator_constants(self):
        # Starter = comms (3); Growth = comms+grading+billing (3+6+8=17).
        tiers = {t["key"]: t for t in pricing_tiers()}
        self.assertEqual(tiers["starter"]["indicative_from"], 3)
        self.assertEqual(tiers["growth"]["indicative_from"], 17)
        # Enterprise is custom (no fabricated number).
        self.assertTrue(tiers["enterprise"]["is_custom"])
        self.assertEqual(tiers["enterprise"]["indicative_from"], 0)

    def test_currency_symbol_swaps_without_fabricated_fx(self):
        usd = {t["key"]: t for t in pricing_tiers("USD")}
        ngn = {t["key"]: t for t in pricing_tiers("NGN")}
        # Same indicative figure, different symbol (no FX conversion invented).
        self.assertEqual(usd["growth"]["indicative_from"], ngn["growth"]["indicative_from"])
        self.assertIn("$", usd["growth"]["price_note"])
        self.assertIn("₦", ngn["growth"]["price_note"])

    def test_unknown_currency_falls_back_to_code_prefix(self):
        tiers = {t["key"]: t for t in pricing_tiers("ZZZ")}
        self.assertIn("ZZZ", tiers["starter"]["price_note"])
