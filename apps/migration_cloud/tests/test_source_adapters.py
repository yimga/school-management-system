"""Wave M (v3.95.0 — 2026-05-26) — Concierge Migration source adapter tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.source_adapters import (
    all_capabilities,
    get_source,
    list_sources,
    sources_for_segment,
    sources_with_capability,
    summary,
    total_concierge_days_for_sources,
)


class SeededRegistryTests(SimpleTestCase):

    def test_seven_sources_seeded(self):
        ids = {s.source_id for s in list_sources()}
        for must in ("powerschool-sis", "sims-capita-ess", "arbor-mis",
                     "bromcom-mis", "managebac-faria", "skyward-sis",
                     "generic-csv"):
            self.assertIn(must, ids)

    def test_get_source_by_id(self):
        s = get_source("powerschool-sis")
        self.assertIsNotNone(s)
        self.assertEqual(s.vendor, "PowerSchool")
        self.assertIn("NA-K12", s.market_segments)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(get_source("nonexistent"))

    def test_each_source_has_at_least_one_transport(self):
        for s in list_sources():
            self.assertGreaterEqual(len(s.transport), 1)

    def test_each_source_has_at_least_one_capability(self):
        for s in list_sources():
            self.assertGreaterEqual(len(s.capabilities), 1)

    def test_capability_values_are_known(self):
        valid = set(all_capabilities())
        for s in list_sources():
            for cap in s.capabilities:
                self.assertIn(cap, valid)

    def test_risk_level_is_known(self):
        for s in list_sources():
            self.assertIn(s.risk_level, {"low", "medium", "high"})

    def test_estimated_days_positive(self):
        for s in list_sources():
            self.assertGreater(s.estimated_concierge_days, 0)


class FilterTests(SimpleTestCase):

    def test_uk_segment_returns_uk_specific_sources(self):
        uk = sources_for_segment("UK-K12")
        ids = {s.source_id for s in uk}
        self.assertIn("sims-capita-ess", ids)
        self.assertIn("arbor-mis", ids)
        self.assertIn("bromcom-mis", ids)
        # PowerSchool is NA only.
        self.assertNotIn("powerschool-sis", ids)

    def test_na_segment_returns_na_specific(self):
        na = sources_for_segment("NA-K12")
        ids = {s.source_id for s in na}
        self.assertIn("powerschool-sis", ids)
        self.assertIn("skyward-sis", ids)

    def test_ib_segment_returns_managebac(self):
        ib = sources_for_segment("IB-Global")
        self.assertIn("managebac-faria", {s.source_id for s in ib})

    def test_incremental_sync_capability_only_arbor(self):
        incremental = sources_with_capability("incremental_sync")
        # Only Arbor supports it in the seed.
        self.assertEqual({s.source_id for s in incremental}, {"arbor-mis"})

    def test_unknown_segment_returns_empty(self):
        self.assertEqual(sources_for_segment("nowhere"), ())


class ConciergeDaysTests(SimpleTestCase):

    def test_sum_concierge_days(self):
        days = total_concierge_days_for_sources(["powerschool-sis", "sims-capita-ess"])
        self.assertEqual(days, 21 + 18)

    def test_unknown_source_id_ignored(self):
        days = total_concierge_days_for_sources(["powerschool-sis", "nonexistent"])
        self.assertEqual(days, 21)

    def test_empty_list_returns_zero(self):
        self.assertEqual(total_concierge_days_for_sources([]), 0)


class SummaryTests(SimpleTestCase):

    def test_summary_shape(self):
        s = summary()
        self.assertIn("source_count", s)
        self.assertIn("all_capabilities", s)
        self.assertIn("by_risk", s)
        self.assertIn("by_segment", s)

    def test_summary_risk_counts(self):
        s = summary()
        # Total of all risk levels should equal source count.
        self.assertEqual(
            s["by_risk"]["low"] + s["by_risk"]["medium"] + s["by_risk"]["high"],
            s["source_count"],
        )
