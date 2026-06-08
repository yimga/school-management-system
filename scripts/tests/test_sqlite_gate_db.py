"""Fast contract tests for the SQLite gate database lease."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "sqlite_gate_db.py"
    spec = importlib.util.spec_from_file_location("sqlite_gate_db_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SQLiteGateLeaseTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "gate.sqlite3"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_lease_blocks_a_second_owner_and_releases(self):
        lock_path = self.mod.sqlite_gate_lock_path(self.db_path)
        with self.mod.sqlite_gate_lease(self.db_path, timeout=0.1):
            self.assertTrue(lock_path.is_dir())
            with self.assertRaises(TimeoutError):
                with self.mod.sqlite_gate_lease(self.db_path, timeout=0.05):
                    pass
        self.assertFalse(lock_path.exists())

    def test_dead_owner_lock_is_recovered(self):
        lock_path = self.mod.sqlite_gate_lock_path(self.db_path)
        lock_path.mkdir()
        (lock_path / "owner.json").write_text(
            json.dumps(
                {
                    "pid": 2_147_483_647,
                    "created_at": 0,
                    "token": "dead-owner",
                }
            ),
            encoding="utf-8",
        )
        with self.mod.sqlite_gate_lease(
            self.db_path,
            timeout=0.1,
            stale_after=0,
        ):
            owner = json.loads(
                (lock_path / "owner.json").read_text(encoding="utf-8")
            )
            self.assertEqual(owner["pid"], os.getpid())
            self.assertNotEqual(owner["token"], "dead-owner")

    def test_fresh_gate_paths_are_unique(self):
        root = Path(self.tempdir.name)
        first = self.mod.ensure_gate_session(root, force_fresh=True)
        second = self.mod.ensure_gate_session(root, force_fresh=True)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
