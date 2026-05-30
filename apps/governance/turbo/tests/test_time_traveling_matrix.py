"""Tests for time_traveling_matrix runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import time_traveling_matrix as ttm


class TimeTravelingMatrixTests(unittest.TestCase):
    def test_runtime_health_passes(self) -> None:
        health = ttm.runtime_health()
        self.assertTrue(health.get("healthy"), msg=health)

    def test_get_as_of_returns_marker(self) -> None:
        sample = next(iter(ttm.SHARD_DIR.glob("*.json")), None)
        self.assertIsNotNone(sample)
        view = ttm.get_as_of(sample.stem)
        self.assertIsNotNone(view)
        self.assertIn("_as_of", view)
        self.assertIn("_iso_alpha2", view)

    def test_unknown_iso_returns_none(self) -> None:
        self.assertIsNone(ttm.get_as_of("ZZ"))

    def test_invalid_date_raises(self) -> None:
        with self.assertRaises(ValueError):
            ttm.get_as_of("US", as_of="not-a-date")
