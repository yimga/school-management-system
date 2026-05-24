"""GEOS Lane 2 evidence scoring helpers."""

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.platform_runtime.geos_lane2_evidence import (
    evidence_json_complete,
    entry_live_satisfied,
    pilot_slot_pct,
)


class GeosLane2EvidenceTests(SimpleTestCase):
    def test_evidence_json_complete_rejects_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(
                json.dumps({"evidence_status": "pending_operator", "id": "pi_…"}),
                encoding="utf-8",
            )
            self.assertFalse(evidence_json_complete(path))

    def test_evidence_json_complete_accepts_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(
                json.dumps({"evidence_status": "verified_live", "payment_id": "abc"}),
                encoding="utf-8",
            )
            self.assertTrue(evidence_json_complete(path))

    def test_entry_live_satisfied_not_required(self):
        self.assertTrue(entry_live_satisfied({"status": "not_required"}))

    def test_pilot_slot_pct_reads_scorecard(self):
        pct = pilot_slot_pct()
        self.assertGreaterEqual(pct, 0.0)
        self.assertLessEqual(pct, 100.0)
