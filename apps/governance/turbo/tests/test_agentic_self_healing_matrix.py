"""Tests for agentic_self_healing_matrix runtime."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.governance.turbo import agentic_self_healing_matrix as ashm


class SelfHealingMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig_queue = ashm.QUEUE_PATH
        ashm.QUEUE_PATH = Path(self.tmp.name) / "queue.json"
        self._orig_shard_dir = ashm.SHARD_DIR
        ashm.SHARD_DIR = Path(self.tmp.name) / "shards"
        ashm.SHARD_DIR.mkdir()
        (ashm.SHARD_DIR / "US.json").write_text(json.dumps({"iso_alpha2": "US"}), encoding="utf-8")

    def tearDown(self) -> None:
        ashm.QUEUE_PATH = self._orig_queue
        ashm.SHARD_DIR = self._orig_shard_dir

    def test_propose_review_apply(self) -> None:
        prop = ashm.propose(iso_alpha2="US", field="ministry_name", new_value="Department of Education", source="watcher:gazette")
        self.assertEqual(prop["status"], "proposed")
        reviewed = ashm.review(prop["proposal_id"], action="approve", reviewer="reviewer@runmycampus.com")
        self.assertEqual(reviewed["status"], "approved")
        applied = ashm.apply_approved()
        self.assertEqual(len(applied), 1)
        row = json.loads((ashm.SHARD_DIR / "US.json").read_text(encoding="utf-8"))
        self.assertEqual(row["ministry_name"], "Department of Education")

    def test_invalid_action_raises(self) -> None:
        prop = ashm.propose(iso_alpha2="US", field="x", new_value="y", source="t")
        with self.assertRaises(ValueError):
            ashm.review(prop["proposal_id"], action="ignore", reviewer="r")
