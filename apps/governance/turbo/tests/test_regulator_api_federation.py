"""Tests for regulator_api_federation runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import regulator_api_federation as raf


class RegulatorAPIFederationTests(unittest.TestCase):
    def test_lookup_supported_country(self) -> None:
        result = raf.lookup("GB", "school_metadata")
        self.assertTrue(result["available"])

    def test_lookup_unsupported_capability(self) -> None:
        result = raf.lookup("GB", "tax_filing")
        self.assertFalse(result["available"])

    def test_lookup_unsupported_country(self) -> None:
        result = raf.lookup("ZZ", "anything")
        self.assertFalse(result["available"])

    def test_call_raises_external_blocked(self) -> None:
        with self.assertRaises(raf.RegulatorAdapterUnavailable):
            raf.call("GB", "school_metadata", {})
