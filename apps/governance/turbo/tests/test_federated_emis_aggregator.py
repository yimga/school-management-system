"""Tests for federated_emis_aggregator runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import federated_emis_aggregator as fem


class FederatedEMISTests(unittest.TestCase):
    def test_aggregate_sums_with_noise(self) -> None:
        rows = [{"enrollment": 100}, {"enrollment": 200}]
        result = fem.aggregate(rows, metric="enrollment", epsilon=1.0, sensitivity=1.0, seed=42)
        self.assertEqual(result["row_count"], 2)
        self.assertIsInstance(result["noised_total"], float)

    def test_epsilon_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            fem.aggregate([], metric="x", epsilon=0.0)
