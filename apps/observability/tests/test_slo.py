"""Tests for the SLO module."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.slo import (
    SLOS,
    SLODefinition,
    burn_rate,
    burn_rate_severity,
    get_slo,
    slos_by_key,
)


class SLODefinitionsTests(SimpleTestCase):
    def test_canonical_slos_present(self):
        keys = {s.key for s in SLOS}
        # The 4 user-journey hotspots + 4 platform SLOs must always exist.
        for required in {
            "web.availability",
            "attendance.submit",
            "grade.entry",
            "parent.dashboard",
            "migration.bundle_apply",
            "ai.gateway.latency",
            "webhook.delivery",
            "sync.conflict_pending",
        }:
            self.assertIn(required, keys, f"missing canonical SLO: {required}")

    def test_lookup_helpers(self):
        index = slos_by_key()
        self.assertIn("attendance.submit", index)
        self.assertEqual(get_slo("attendance.submit").threshold_ms, 800)
        self.assertIsNone(get_slo("does-not-exist"))

    def test_latency_slos_have_threshold(self):
        for slo in SLOS:
            if slo.kind in ("latency_p95", "latency_p99"):
                self.assertIsNotNone(
                    slo.threshold_ms,
                    f"{slo.key} is a latency SLO without threshold_ms",
                )


class BurnRateTests(SimpleTestCase):
    def _slo(self, target: float = 99.9) -> SLODefinition:
        return SLODefinition(
            key="test.slo", label="test", kind="availability",
            target=target, window_days=30,
        )

    def test_zero_error_zero_burn(self):
        self.assertEqual(burn_rate(actual_error_rate=0.0, slo=self._slo(), window_minutes=60), 0.0)

    def test_at_budget_is_one(self):
        # target 99.9% → budget 0.001. error_rate 0.001 → burn 1.0
        b = burn_rate(actual_error_rate=0.001, slo=self._slo(99.9), window_minutes=60)
        self.assertAlmostEqual(b, 1.0, places=6)

    def test_fast_burn(self):
        # error_rate 1.5% on a 99.9% SLO is 15x the budget.
        b = burn_rate(actual_error_rate=0.015, slo=self._slo(99.9), window_minutes=60)
        self.assertGreaterEqual(b, 14.4)
        self.assertEqual(burn_rate_severity(burn=b, window_minutes=60), "page")

    def test_ticket_burn(self):
        # error_rate at 4x budget over 6h window → ticket, not page
        b = burn_rate(actual_error_rate=0.004, slo=self._slo(99.9), window_minutes=360)
        self.assertEqual(burn_rate_severity(burn=b, window_minutes=360), "ticket")

    def test_ok_below_half_budget(self):
        b = burn_rate(actual_error_rate=0.0004, slo=self._slo(99.9), window_minutes=4320)
        self.assertEqual(burn_rate_severity(burn=b, window_minutes=4320), "ok")

    def test_zero_budget_returns_inf_when_errors(self):
        slo = self._slo(100.0)
        self.assertEqual(burn_rate(actual_error_rate=0.001, slo=slo, window_minutes=60), float("inf"))
        self.assertEqual(burn_rate(actual_error_rate=0.0, slo=slo, window_minutes=60), 0.0)
