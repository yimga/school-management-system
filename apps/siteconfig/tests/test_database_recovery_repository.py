"""
Tests for siteconfig.repositories.database_recovery_repository (§2.4 raw SQL wrap).
Non-existent path returns None; valid SQLite file returns 'ok' or error string.
"""

import tempfile
import unittest
from pathlib import Path

from apps.siteconfig.repositories.database_recovery_repository import (
    run_sqlite_integrity_check,
)


class TestDatabaseRecoveryRepository(unittest.TestCase):
    """SQLite integrity check: missing path → None; valid DB → 'ok'."""

    def test_nonexistent_path_returns_none(self):
        self.assertIsNone(run_sqlite_integrity_check(Path("/nonexistent/db.sqlite3")))
        self.assertIsNone(run_sqlite_integrity_check("/nonexistent/db.sqlite3"))

    def test_valid_sqlite_returns_ok(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            import sqlite3

            conn = sqlite3.connect(str(path))
            conn.execute("CREATE TABLE t (id INTEGER);")
            conn.close()
            self.assertEqual(run_sqlite_integrity_check(path), "ok")
        finally:
            path.unlink(missing_ok=True)
