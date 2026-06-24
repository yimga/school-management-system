"""Multi-currency rollup for holding companies (B4).

Aggregates a holding company's active sub-schools' billing by currency with NO
FX conversion (honest per-currency buckets) and materializes the result into
HoldingCurrencyRollup rows. The per-school pricing is patched here so these
tests exercise B4's aggregation/persistence, not the (separately tested) pricing
internals.
"""
from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.billing import holding_rollup
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import HoldingCurrencyRollup, Plan

# Per-child priced result, keyed by slug.
PRICES = {
    "sub-a": {"total": Decimal("100.00"), "currency_code": "USD"},
    "sub-b": {"total": Decimal("200.00"), "currency_code": "USD"},
    "sub-c": {"total": Decimal("15000.00"), "currency_code": "NGN"},
    "sub-zero": {"total": Decimal("0.00"), "currency_code": "USD"},
}


def _fake_price(school, plan, **kwargs):
    return PRICES.get(school.slug, {"total": Decimal("0.00"), "currency_code": "USD"})


class HoldingCurrencyRollupTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pro", slug="pro-b4", base_price=Decimal("100.00"), is_active=True
        )
        self.holding = School.objects.create(
            name="holding", slug="holding-b4", subdomain="holding-b4", is_active=True
        )

    def _child(self, slug, *, plan=True, active=True):
        return School.objects.create(
            name=slug,
            slug=slug,
            subdomain=slug,
            is_active=active,
            parent_school=self.holding,
            plan=self.plan if plan else None,
        )

    @mock.patch("apps.billing.services.compute_subscription_price_for_school", _fake_price)
    def test_totals_grouped_by_currency_no_fx(self):
        self._child("sub-a")
        self._child("sub-b")
        self._child("sub-c")
        totals = holding_rollup.compute_holding_currency_totals(self.holding)
        self.assertEqual(set(totals), {"USD", "NGN"})
        self.assertEqual(totals["USD"]["total"], Decimal("300.00"))
        self.assertEqual(totals["USD"]["count"], 2)
        self.assertEqual(totals["NGN"]["total"], Decimal("15000.00"))
        self.assertEqual(totals["NGN"]["count"], 1)

    @mock.patch("apps.billing.services.compute_subscription_price_for_school", _fake_price)
    def test_skips_no_plan_and_nonpositive_total(self):
        self._child("sub-a")
        self._child("sub-no-plan", plan=False)
        self._child("sub-zero")
        totals = holding_rollup.compute_holding_currency_totals(self.holding)
        self.assertEqual(set(totals), {"USD"})
        self.assertEqual(totals["USD"]["total"], Decimal("100.00"))
        self.assertEqual(totals["USD"]["count"], 1)

    @mock.patch("apps.billing.services.compute_subscription_price_for_school", _fake_price)
    def test_inactive_children_excluded(self):
        self._child("sub-a")
        self._child("sub-b", active=False)
        totals = holding_rollup.compute_holding_currency_totals(self.holding)
        self.assertEqual(totals["USD"]["count"], 1)

    @mock.patch("apps.billing.services.compute_subscription_price_for_school", _fake_price)
    def test_materialize_creates_rows_per_currency(self):
        self._child("sub-a")
        self._child("sub-c")
        holding_rollup.materialize_holding_currency_rollups(self.holding)
        rows = {
            r.currency_code: r
            for r in HoldingCurrencyRollup.objects.filter(parent_school=self.holding)
        }
        self.assertEqual(set(rows), {"USD", "NGN"})
        self.assertEqual(rows["USD"].total_amount, Decimal("100.00"))
        self.assertEqual(rows["NGN"].total_amount, Decimal("15000.00"))
        self.assertEqual(rows["NGN"].source_school_count, 1)
        self.assertIsNotNone(rows["USD"].as_of)

    @mock.patch("apps.billing.services.compute_subscription_price_for_school", _fake_price)
    def test_rematerialize_prunes_stale_currency(self):
        a = self._child("sub-a")
        c = self._child("sub-c")
        holding_rollup.materialize_holding_currency_rollups(self.holding)
        self.assertTrue(
            HoldingCurrencyRollup.objects.filter(
                parent_school=self.holding, currency_code="NGN"
            ).exists()
        )
        # Remove the only NGN contributor and refresh.
        c.delete()
        holding_rollup.materialize_holding_currency_rollups(self.holding)
        self.assertFalse(
            HoldingCurrencyRollup.objects.filter(
                parent_school=self.holding, currency_code="NGN"
            ).exists()
        )
        self.assertTrue(
            HoldingCurrencyRollup.objects.filter(
                parent_school=self.holding, currency_code="USD"
            ).exists()
        )
        self.assertIsNotNone(a.pk)

    def test_no_children_returns_empty(self):
        self.assertEqual(holding_rollup.compute_holding_currency_totals(self.holding), {})

    def test_none_parent_is_safe(self):
        self.assertEqual(holding_rollup.compute_holding_currency_totals(None), {})
        self.assertEqual(holding_rollup.materialize_holding_currency_rollups(None), {})

    @mock.patch("apps.billing.services.compute_subscription_price_for_school", _fake_price)
    def test_materialize_all_refreshes_holding_parents(self):
        self._child("sub-a")
        self._child("sub-c")
        summary = holding_rollup.materialize_all_holding_currency_rollups()
        self.assertGreaterEqual(summary["parents_refreshed"], 1)
        self.assertGreaterEqual(summary["currency_buckets"], 2)
