"""Tests for sovereignty_trust_score runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import sovereignty_trust_score as sts


class SovereigntyTrustScoreTests(unittest.TestCase):
    def test_compute_score_for_known_iso(self) -> None:
        result = sts.compute_score("GB")
        self.assertIn("score", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_compute_score_for_missing_iso(self) -> None:
        result = sts.compute_score("ZZ")
        self.assertEqual(result.get("tier"), "evidence_required")

    def test_runtime_health(self) -> None:
        self.assertTrue(sts.runtime_health().get("healthy"))
