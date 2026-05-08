"""Tests for the expanded payment region catalog (Surface 1.3)."""

from __future__ import annotations

import unittest

from apps.finance.payment_region_catalog import (
    CANONICAL_PAYMENT_ORCHESTRATION_ISO2,
    _RAIL_DEFAULTS,
    _REGION_NAMES,
)
from apps.locale.phone_formats import (
    PHONE_FORMATS,
    dial_code,
    phone_placeholder,
)


class CatalogExpansionTests(unittest.TestCase):
    def test_at_least_eleven_iso2_codes(self):
        self.assertGreaterEqual(len(CANONICAL_PAYMENT_ORCHESTRATION_ISO2), 11)

    def test_every_iso2_has_rail_defaults(self):
        for iso2 in CANONICAL_PAYMENT_ORCHESTRATION_ISO2:
            self.assertIn(iso2, _RAIL_DEFAULTS, f"Missing rail defaults for {iso2}")
            spec = _RAIL_DEFAULTS[iso2]
            self.assertIn("primary", spec)
            self.assertIn("backup", spec)
            self.assertTrue(spec["primary"]["code"])
            self.assertTrue(spec["backup"]["code"])

    def test_every_iso2_has_region_name(self):
        for iso2 in CANONICAL_PAYMENT_ORCHESTRATION_ISO2:
            self.assertIn(iso2, _REGION_NAMES)

    def test_cameroon_remains_supported(self):
        self.assertIn("CM", CANONICAL_PAYMENT_ORCHESTRATION_ISO2)
        self.assertEqual(_RAIL_DEFAULTS["CM"]["primary"]["code"], "cm-mtn")

    def test_nigeria_uses_paystack_primary(self):
        self.assertIn("NG", CANONICAL_PAYMENT_ORCHESTRATION_ISO2)
        self.assertEqual(_RAIL_DEFAULTS["NG"]["primary"]["code"], "ng-paystack")

    def test_kenya_uses_mpesa_primary(self):
        self.assertEqual(_RAIL_DEFAULTS["KE"]["primary"]["code"], "ke-mpesa")


class PhoneFormatTests(unittest.TestCase):
    def test_known_iso2_returns_specific_placeholder(self):
        self.assertEqual(phone_placeholder("CM"), "+237 6XX XXX XXX")
        self.assertEqual(phone_placeholder("NG"), "+234 8XX XXX XXXX")
        self.assertEqual(phone_placeholder("US"), "+1 (XXX) XXX-XXXX")

    def test_unknown_iso2_returns_neutral_placeholder(self):
        self.assertEqual(phone_placeholder("ZZ"), "+CC NNN NNN NNNN")

    def test_empty_iso2_returns_neutral(self):
        self.assertEqual(phone_placeholder(""), "+CC NNN NNN NNNN")
        self.assertEqual(phone_placeholder(None), "+CC NNN NNN NNNN")

    def test_dial_code_known(self):
        self.assertEqual(dial_code("GH"), "+233")
        self.assertEqual(dial_code("ZA"), "+27")

    def test_dial_code_unknown_empty(self):
        self.assertEqual(dial_code("ZZ"), "")

    def test_table_size_at_least_supported_corridors(self):
        # All payment-catalog ISO2 codes must be present in PHONE_FORMATS.
        for iso2 in CANONICAL_PAYMENT_ORCHESTRATION_ISO2:
            self.assertIn(iso2, PHONE_FORMATS, f"Phone format missing for {iso2}")


if __name__ == "__main__":
    unittest.main()
