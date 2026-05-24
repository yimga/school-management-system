"""SFDP 1423 — regional_payment_profiles.json parity with catalog ISO2."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from apps.finance.payment_region_catalog import CANONICAL_PAYMENT_ORCHESTRATION_ISO2
from apps.finance.regional_payment_profiles import get_regional_profile


class RegionalPaymentProfilesCatalogDriftTests(unittest.TestCase):
    def test_every_canonical_iso2_has_json_profile(self):
        for iso2 in sorted(CANONICAL_PAYMENT_ORCHESTRATION_ISO2):
            row = get_regional_profile(iso2)
            self.assertIsNotNone(row, msg=f"missing JSON profile for {iso2}")
            self.assertEqual(row.get("country_code"), iso2)
            self.assertTrue(row.get("primary_rail"))
            self.assertTrue(row.get("backup_rail"))

    def test_json_file_parses_and_covers_catalog(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "regional_payment_profiles.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = sorted(CANONICAL_PAYMENT_ORCHESTRATION_ISO2 - set(data.keys()))
        self.assertEqual(missing, [], msg=f"catalog ISO2 missing from JSON: {missing}")
