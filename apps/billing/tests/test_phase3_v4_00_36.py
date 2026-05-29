"""v4.00.36 Phase 3 — unit tests for the 10X tier modules."""

from __future__ import annotations

from datetime import date as _date_cls, datetime, timezone as _tz
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase

from apps.billing import realtime_meter, multi_tier_ledger, psp_routing, tax_engine
from apps.billing import usage_caps


# ----------- realtime_meter ------------------------------------------------


class HotIncrementTests(SimpleTestCase):
    def test_none_school_is_noop(self):
        with mock.patch.object(realtime_meter, "_redis_client", return_value=mock.Mock()):
            realtime_meter.hot_increment(None, "ai_invocations", 5)

    def test_unknown_dimension_is_noop(self):
        school = mock.Mock(pk=1)
        with mock.patch.object(
            realtime_meter, "_redis_client", return_value=mock.Mock()
        ) as cli:
            realtime_meter.hot_increment(school, "not_a_dimension", 5)
        cli.return_value.hincrby.assert_not_called()

    def test_zero_delta_is_noop(self):
        school = mock.Mock(pk=1)
        with mock.patch.object(
            realtime_meter, "_redis_client", return_value=mock.Mock()
        ) as cli:
            realtime_meter.hot_increment(school, "ai_invocations", 0)
        cli.return_value.hincrby.assert_not_called()

    def test_redis_hincrby_called_when_available(self):
        school = mock.Mock(pk=42)
        client = mock.Mock()
        with mock.patch.object(realtime_meter, "_redis_client", return_value=client):
            realtime_meter.hot_increment(school, "ai_invocations", 7)
        client.hincrby.assert_called_once()
        client.expire.assert_called_once()
        # Hash key should embed today + tenant pk.
        called_key = client.hincrby.call_args.args[0]
        self.assertIn(":42", called_key)
        self.assertTrue(called_key.startswith("billing:hot:"))

    def test_falls_back_to_orm_when_no_redis(self):
        school = mock.Mock(pk=42)
        with mock.patch.object(
            realtime_meter, "_redis_client", return_value=None
        ), mock.patch("apps.billing.models_metering.record") as record_mock:
            realtime_meter.hot_increment(school, "ai_invocations", 7)
        record_mock.assert_called_once_with(school, "ai_invocations", delta=7)


class FlushHotBuffersTests(SimpleTestCase):
    def test_no_redis_client_returns_zero(self):
        with mock.patch.object(realtime_meter, "_redis_client", return_value=None):
            out = realtime_meter.flush_hot_buffers()
        self.assertEqual(out, {"keys_seen": 0, "flushed": 0, "ticks_written": 0})


class ParseHotKeyTests(SimpleTestCase):
    def test_well_formed_parses(self):
        result = realtime_meter._parse_hot_key("billing:hot:2026-05-29:42")
        self.assertEqual(result, (_date_cls(2026, 5, 29), 42))

    def test_bad_prefix_returns_none(self):
        self.assertIsNone(realtime_meter._parse_hot_key("other:hot:2026-05-29:42"))

    def test_wrong_parts_returns_none(self):
        self.assertIsNone(realtime_meter._parse_hot_key("billing:hot:2026-05-29"))


# ----------- usage_caps ----------------------------------------------------


class EvaluateCapTests(SimpleTestCase):
    def test_none_school_is_no_cap(self):
        verdict = usage_caps.evaluate_cap(None, "ai_invocations")
        self.assertEqual(verdict.band, "no_cap")

    def test_no_cap_row_returns_no_cap(self):
        school = mock.Mock(pk=1)
        with mock.patch.object(
            usage_caps.UsageCap.objects, "filter"
        ) as filter_mock:
            filter_mock.return_value.first.return_value = None
            verdict = usage_caps.evaluate_cap(school, "ai_invocations")
        self.assertEqual(verdict.band, "no_cap")
        self.assertFalse(verdict.is_warned)
        self.assertFalse(verdict.is_capped)

    def test_soft_warn_band(self):
        school = mock.Mock(pk=1)
        cap = mock.Mock(soft_warn_at=80, hard_cap=100, period_grain="day")
        with mock.patch.object(
            usage_caps.UsageCap.objects, "filter"
        ) as cap_filter, mock.patch(
            "apps.billing.models.UsageMeter.objects.filter"
        ) as meter_filter:
            cap_filter.return_value.first.return_value = cap
            meter_filter.return_value.values_list.return_value = [85]
            verdict = usage_caps.evaluate_cap(school, "ai_invocations")
        self.assertEqual(verdict.band, "soft_warn")
        self.assertTrue(verdict.is_warned)
        self.assertFalse(verdict.is_capped)

    def test_hard_cap_band(self):
        school = mock.Mock(pk=1)
        cap = mock.Mock(soft_warn_at=80, hard_cap=100, period_grain="day")
        with mock.patch.object(
            usage_caps.UsageCap.objects, "filter"
        ) as cap_filter, mock.patch(
            "apps.billing.models.UsageMeter.objects.filter"
        ) as meter_filter:
            cap_filter.return_value.first.return_value = cap
            meter_filter.return_value.values_list.return_value = [120]
            verdict = usage_caps.evaluate_cap(school, "ai_invocations")
        self.assertEqual(verdict.band, "hard_cap")
        self.assertTrue(verdict.is_capped)


# ----------- psp_routing ---------------------------------------------------


class RankPSPsTests(SimpleTestCase):
    def test_currency_match_outranks_no_match_for_cards(self):
        rows = psp_routing.rank_psps(
            country_code="US", currency="USD", capability="cards"
        )
        self.assertGreater(len(rows), 0)
        # Top candidate must settle USD AND support cards.
        top = rows[0]
        self.assertTrue(top.matched_currency, f"top={top.psp.psp_slug} should match USD")
        self.assertTrue(top.matched_capability, f"top={top.psp.psp_slug} should support cards")

    def test_africa_routing_picks_african_psp(self):
        rows = psp_routing.rank_psps(
            country_code="NG", currency="NGN", capability="cards"
        )
        top = rows[0].psp
        self.assertEqual(top.region, "africa")

    def test_mobile_money_routes_to_momo_psp(self):
        rows = psp_routing.rank_psps(
            country_code="CM", currency="XAF", capability="mobile_money"
        )
        top = rows[0].psp
        self.assertIn("mobile_money", {c.lower() for c in top.capabilities})

    def test_planned_excluded_when_only_live_inprogress_eligible(self):
        rows = psp_routing.rank_psps(
            country_code="US", currency="USD", capability="cards",
            eligible_statuses=("live", "in_progress"),
        )
        for c in rows:
            self.assertIn(c.psp.adapter_status, {"live", "in_progress"})


class RoutePaymentTests(SimpleTestCase):
    def test_primary_and_fallback_disjoint(self):
        result = psp_routing.route_payment(
            country_code="NG", currency="NGN", capability="cards",
            fallback_capabilities=("mobile_money",),
        )
        primary_slugs = {c.psp.psp_slug for c in result["primary"]}
        fallback_slugs = {c.psp.psp_slug for c in result["fallback"]}
        self.assertFalse(primary_slugs & fallback_slugs)


# ----------- multi_tier_ledger ---------------------------------------------


class RollupAccountBalanceTests(SimpleTestCase):
    def test_no_children_returns_empty_rollup(self):
        parent = mock.Mock(pk=1, currency_code="USD")
        with mock.patch(
            "apps.billing.models.BillingAccount.objects.filter"
        ) as ba_filter:
            ba_filter.return_value = []
            rollup = multi_tier_ledger.rollup_account_balance(parent)
        self.assertEqual(rollup.grand_total_parent, Decimal("0.00"))
        self.assertEqual(len(rollup.lines), 0)

    def test_same_currency_child_aggregates_one_to_one(self):
        parent = mock.Mock(pk=1, currency_code="USD")
        child = mock.Mock(pk=2, currency_code="USD")
        child.school = mock.Mock()
        child.school.name = "Child Campus"
        entry = mock.Mock(
            amount=Decimal("250.00"),
            entry_type="CHARGE",
            status="POSTED",
            happened_at=datetime(2026, 5, 1, tzinfo=_tz.utc),
            reference="INV-1",
        )
        qs = mock.Mock()
        qs.iterator.return_value = iter([entry])
        qs.filter.return_value = qs
        with mock.patch(
            "apps.billing.models.BillingAccount.objects.filter"
        ) as ba_filter, mock.patch(
            "apps.billing.models.PlatformLedgerEntry.objects.filter"
        ) as ple_filter:
            ba_filter.return_value = [child]
            ple_filter.return_value = qs
            rollup = multi_tier_ledger.rollup_account_balance(parent)
        self.assertEqual(rollup.grand_total_parent, Decimal("250.00"))
        self.assertEqual(len(rollup.lines), 1)
        self.assertEqual(rollup.totals_by_type["CHARGE"], Decimal("250.00"))

    def test_unresolved_currency_pair_recorded(self):
        parent = mock.Mock(pk=1, currency_code="USD")
        child = mock.Mock(pk=2, currency_code="XAF")
        with mock.patch(
            "apps.billing.models.BillingAccount.objects.filter"
        ) as ba_filter, mock.patch(
            "apps.billing.models.PlatformLedgerEntry.objects.filter"
        ) as ple_filter:
            ba_filter.return_value = [child]
            ple_filter.return_value = mock.Mock()
            rollup = multi_tier_ledger.rollup_account_balance(parent)
        self.assertEqual(rollup.unresolved_currency_pairs, [("XAF", "USD")])
        self.assertEqual(len(rollup.lines), 0)

    def test_custom_fx_resolver_used(self):
        parent = mock.Mock(pk=1, currency_code="USD")
        child = mock.Mock(pk=2, currency_code="EUR")
        child.school = mock.Mock()
        child.school.name = "EU Campus"
        entry = mock.Mock(
            amount=Decimal("100.00"),
            entry_type="CHARGE",
            status="POSTED",
            happened_at=datetime(2026, 5, 1, tzinfo=_tz.utc),
            reference="INV-2",
        )
        qs = mock.Mock()
        qs.iterator.return_value = iter([entry])
        qs.filter.return_value = qs

        def fx(source: str, target: str):
            if source == "EUR" and target == "USD":
                return Decimal("1.10")
            return None

        with mock.patch(
            "apps.billing.models.BillingAccount.objects.filter"
        ) as ba_filter, mock.patch(
            "apps.billing.models.PlatformLedgerEntry.objects.filter"
        ) as ple_filter:
            ba_filter.return_value = [child]
            ple_filter.return_value = qs
            rollup = multi_tier_ledger.rollup_account_balance(parent, fx_resolver=fx)
        self.assertEqual(rollup.grand_total_parent, Decimal("110.00"))


# ----------- tax_engine ----------------------------------------------------


class TaxEngineTests(SimpleTestCase):
    def setUp(self):
        # Snapshot state so registry pollution doesn't leak between tests.
        self._saved = dict(tax_engine._RESOLVERS)
        self._saved_active = tax_engine._ACTIVE_NAME

    def tearDown(self):
        tax_engine._RESOLVERS.clear()
        tax_engine._RESOLVERS.update(self._saved)
        tax_engine._ACTIVE_NAME = self._saved_active

    def test_static_resolver_reads_country_multiplier(self):
        row = mock.Mock()
        row.tax_rate = Decimal("0.18")
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.CountryMultiplier.objects.filter"
        ) as cm:
            cm.return_value.only.return_value.first.return_value = row
            rate = tax_engine.static_tax_resolver("IN")
        self.assertEqual(rate, Decimal("0.18"))

    def test_active_resolver_used_first(self):
        called: list[tuple] = []

        def fake(country_code, *, subdivision_code=None, line_amount=None):
            called.append((country_code, subdivision_code))
            return Decimal("0.25")

        tax_engine.register_tax_resolver("fake", fake)
        tax_engine.set_active_resolver("fake")
        rate = tax_engine.resolve_tax_rate("US", subdivision_code="CA")
        self.assertEqual(rate, Decimal("0.25"))
        self.assertEqual(called, [("US", "CA")])

    def test_active_returns_none_falls_back_to_static(self):
        def fake_none(country_code, *, subdivision_code=None, line_amount=None):
            return None

        tax_engine.register_tax_resolver("fake_none", fake_none)
        tax_engine.set_active_resolver("fake_none")
        row = mock.Mock()
        row.tax_rate = Decimal("0.05")
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.CountryMultiplier.objects.filter"
        ) as cm:
            cm.return_value.only.return_value.first.return_value = row
            rate = tax_engine.resolve_tax_rate("US")
        self.assertEqual(rate, Decimal("0.05"))
