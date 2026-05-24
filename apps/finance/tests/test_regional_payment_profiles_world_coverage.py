"""SFDP — >=200 ISO2 rows in regional_payment_profiles.json."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class RegionalPaymentProfilesWorldCoverageTests(unittest.TestCase):
    def test_at_least_200_country_profiles(self):
        path = Path(__file__).resolve().parents[1] / "data" / "regional_payment_profiles.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data), 200, msg=f"only {len(data)} countries in JSON")
