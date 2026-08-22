"""Tests for apply stall timeout resolution and lander pulse hook."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from apps.migration_cloud.apply_stall import (
    maybe_stall_pulse,
    read_with_stall_pulse,
    resolve_applying_stale_seconds,
    resolve_stall_timeout_seconds,
    stall_pulse_scope,
)


class ResolveStallTimeoutTests(unittest.TestCase):
    @mock.patch("apps.migration_cloud.defaults.get")
    @mock.patch("apps.migration_cloud.unified_progress.expected_row_total")
    def test_scales_by_tier_and_rows(self, row_total, mc_get):
        row_total.return_value = 5000
        mc_get.side_effect = lambda key: {
            "migration_cloud.apply.stall_timeout_seconds": {
                "small": 120,
                "mid": 240,
                "large": 360,
                "state": 600,
            },
            "migration_cloud.apply.stall_timeout_row_scale_per_1000": 30,
            "migration_cloud.apply.stall_timeout_min_seconds": 90,
            "migration_cloud.apply.stall_timeout_max_seconds": 900,
        }[key]
        bundle = SimpleNamespace(pk=1, sla_tier="large")
        self.assertEqual(resolve_stall_timeout_seconds(bundle), 360.0 + 5 * 30.0)

    @mock.patch("apps.migration_cloud.defaults.get")
    @mock.patch("apps.migration_cloud.unified_progress.expected_row_total")
    def test_clamps_to_max(self, row_total, mc_get):
        row_total.return_value = 50_000_000
        mc_get.side_effect = lambda key: {
            "migration_cloud.apply.stall_timeout_seconds": {"small": 120},
            "migration_cloud.apply.stall_timeout_row_scale_per_1000": 1000,
            "migration_cloud.apply.stall_timeout_min_seconds": 90,
            "migration_cloud.apply.stall_timeout_max_seconds": 900,
        }[key]
        bundle = SimpleNamespace(pk=1, sla_tier="small")
        self.assertEqual(resolve_stall_timeout_seconds(bundle), 900.0)


class StallPulseHookTests(unittest.TestCase):
    def test_scope_invokes_hook(self):
        calls: list[str] = []

        def _hook() -> None:
            calls.append("ok")

        with stall_pulse_scope(_hook):
            maybe_stall_pulse()
        self.assertEqual(calls, ["ok"])

    def test_every_throttles_hook(self):
        calls: list[int] = []

        with stall_pulse_scope(lambda: calls.append(1)):
            for i in range(5):
                maybe_stall_pulse(every=2, counter=i)
        self.assertEqual(len(calls), 3)


class ReadWithStallPulseTests(unittest.TestCase):
    def test_reads_in_chunks_and_pulses(self):
        calls: list[int] = []

        class _Stream:
            def __init__(self) -> None:
                self._parts = [b"a" * 512, b"b" * 512, b""]

            def read(self, size: int) -> bytes:
                if not self._parts:
                    return b""
                return self._parts.pop(0)

        with stall_pulse_scope(lambda: calls.append(1)):
            payload = read_with_stall_pulse(_Stream(), chunk_size=512)
        self.assertEqual(payload, (b"a" * 512) + (b"b" * 512))
        self.assertGreaterEqual(len(calls), 2)


class ApplyingStaleThresholdTests(unittest.TestCase):
    @mock.patch("apps.migration_cloud.defaults.get")
    @mock.patch("apps.migration_cloud.unified_progress.expected_row_total")
    @mock.patch("apps.migration_cloud.apply_stall.resolve_stall_timeout_seconds")
    def test_stale_outlives_stall_timeout(self, stall_timeout, row_total, mc_get):
        stall_timeout.return_value = 240.0
        row_total.return_value = 0
        mc_get.side_effect = lambda key: {
            "migration_cloud.repair.applying_stale_seconds": {"small": 600},
            "migration_cloud.repair.applying_stale_row_scale_per_1000": 0,
            "migration_cloud.repair.applying_stale_min_seconds": 300,
            "migration_cloud.repair.applying_stale_max_seconds": 1800,
        }[key]
        bundle = SimpleNamespace(pk=1, sla_tier="small")
        self.assertGreaterEqual(resolve_applying_stale_seconds(bundle), 240.0 * 2.0 + 120.0)


if __name__ == "__main__":
    unittest.main()
