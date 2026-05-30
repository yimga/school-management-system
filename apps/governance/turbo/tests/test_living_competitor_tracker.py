"""Tests for living_competitor_tracker runtime."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.governance.turbo import living_competitor_tracker as lct


class CompetitorTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig_snapshot = lct.SNAPSHOT_PATH
        self._orig_delta = lct.DELTA_PATH
        lct.SNAPSHOT_PATH = Path(self.tmp.name) / "snap.json"
        lct.DELTA_PATH = Path(self.tmp.name) / "delta.json"
        lct.SNAPSHOT_PATH.write_text(json.dumps({"competitors": [{"name": "PowerSchool", "features": ["multi_tenant_isolation", "districts"]}]}), encoding="utf-8")

    def tearDown(self) -> None:
        lct.SNAPSHOT_PATH = self._orig_snapshot
        lct.DELTA_PATH = self._orig_delta

    def test_compute_delta(self) -> None:
        report = lct.compute_delta()
        self.assertEqual(report["competitor_count"], 1)
        delta = report["deltas"][0]
        self.assertIn("districts", delta["they_have_we_dont"])
        self.assertIn("multi_tenant_isolation", delta["shared"])
