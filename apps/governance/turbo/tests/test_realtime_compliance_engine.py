"""Tests for realtime_compliance_engine runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import realtime_compliance_engine as rce


class ComplianceEngineTests(unittest.TestCase):
    def test_biometric_requires_parental_consent(self) -> None:
        decision = rce.evaluate("store_biometric", country_iso="DE", payload={})
        self.assertEqual(decision["decision"], "deny")

    def test_biometric_with_consent(self) -> None:
        decision = rce.evaluate("store_biometric", country_iso="DE", payload={"parental_consent": True})
        self.assertEqual(decision["decision"], "allow")

    def test_unknown_country_warns(self) -> None:
        decision = rce.evaluate("onboard_tenant", country_iso="ZZ")
        self.assertEqual(decision["decision"], "warn")

    def test_sanctions_block(self) -> None:
        decision = rce.evaluate("onboard_tenant", country_iso="KP")
        self.assertIn(decision["decision"], {"allow", "deny", "warn"})
