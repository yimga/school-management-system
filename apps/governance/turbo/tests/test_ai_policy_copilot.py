"""Tests for ai_policy_copilot runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import ai_policy_copilot as cop


class AIPolicyCopilotTests(unittest.TestCase):
    def test_biometric_question(self) -> None:
        result = cop.answer("Can I store fingerprints for attendance?", country_iso="US")
        self.assertEqual(result["intent"], "biometric")

    def test_retention_question(self) -> None:
        result = cop.answer("How long must I keep transcripts?", country_iso="US")
        self.assertEqual(result["intent"], "retention")

    def test_honest_refusal_for_unknown_intent(self) -> None:
        result = cop.answer("What is the weather today?", country_iso="US")
        self.assertTrue(result.get("honest_refusal"))

    def test_honest_refusal_for_missing_shard(self) -> None:
        result = cop.answer("biometric?", country_iso="ZZ")
        self.assertTrue(result.get("honest_refusal"))
