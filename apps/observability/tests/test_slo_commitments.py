"""Public SLO commitments for the status page (T1).

Pure SimpleTestCase — reads the in-process SLO registry, no database. Asserts the
status page is shown TARGETS only (never fabricated live measurements).
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability import slo
from apps.observability.slo import slo_commitments_for_display


class SloCommitmentsTests(SimpleTestCase):
    def test_one_row_per_slo_with_required_keys(self):
        rows = slo_commitments_for_display()
        self.assertEqual(len(rows), len(slo.SLOS))
        required = {"key", "label", "kind", "target_pct", "window_days", "objective"}
        for r in rows:
            self.assertTrue(required <= set(r), f"missing keys in {r.get('key')}")

    def test_targets_only_no_live_measurement_fields(self):
        # Honesty: commitments must never carry a "current"/"actual" value that
        # would imply a live measurement the page can't back.
        forbidden = {"current", "actual", "measured", "value", "status"}
        for r in slo_commitments_for_display():
            self.assertFalse(forbidden & set(r), f"{r['key']} leaks a live-value key")

    def test_latency_objective_mentions_threshold_ms(self):
        rows = {r["key"]: r for r in slo_commitments_for_display()}
        att = rows["attendance.submit"]  # 800ms p95
        self.assertIn("800 ms", att["objective"])
        self.assertIn("p95", att["objective"])
        self.assertEqual(att["target_pct"], 95.0)

    def test_availability_objective_mentions_window(self):
        rows = {r["key"]: r for r in slo_commitments_for_display()}
        web = rows["web.availability"]  # 99.9% / 30d
        self.assertIn("99.9%", web["objective"])
        self.assertIn("30-day", web["objective"])

    def test_target_pct_matches_registry(self):
        rows = {r["key"]: r for r in slo_commitments_for_display()}
        for s in slo.SLOS:
            self.assertEqual(rows[s.key]["target_pct"], s.target)
