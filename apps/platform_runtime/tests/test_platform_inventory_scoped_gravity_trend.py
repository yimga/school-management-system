"""Committed scoped gravity trend file stays aligned with platform_inventory.json."""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase


class ScopedGravityTrendInventoryTests(SimpleTestCase):
    def test_scoped_gravity_trend_last_point_matches_platform_inventory(self):
        root = Path(__file__).resolve().parents[3]
        inv_path = root / "docs" / "generated" / "platform_inventory.json"
        trend_path = root / "scripts" / "generated" / "scoped_gravity_trend.json"
        if not inv_path.is_file():
            self.skipTest("docs/generated/platform_inventory.json missing")
        if not trend_path.is_file():
            self.skipTest("scripts/generated/scoped_gravity_trend.json missing")
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        trend = json.loads(trend_path.read_text(encoding="utf-8"))
        scoped = inv.get("scoped_gravity_counts") or {}
        expected = {str(k): int(v) for k, v in sorted(scoped.items())}
        hist = trend.get("history")
        self.assertIsInstance(hist, list)
        self.assertTrue(hist, msg="scoped_gravity_trend.json history is empty")
        last = hist[-1]
        self.assertIsInstance(last, dict)
        self.assertEqual(last.get("counts"), expected)
