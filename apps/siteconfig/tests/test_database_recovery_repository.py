"""
Tests for siteconfig.repositories.database_recovery_repository (§2.4 raw SQL wrap).
Non-existent path returns None; valid SQLite file returns 'ok' or error string.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.siteconfig.repositories.database_recovery_repository import (
    _MAX_SQLITE_INTEGRITY_CHECK_RESULT_LEN,
    _SQLITE_INTEGRITY_CONNECT_TIMEOUT_SEC,
    run_sqlite_integrity_check,
)


class TestDatabaseRecoveryRepository(unittest.TestCase):
    """SQLite integrity check: missing path → None; valid DB → 'ok'."""

    def test_nonexistent_path_returns_none(self):
        self.assertIsNone(run_sqlite_integrity_check(Path("/nonexistent/db.sqlite3")))
        self.assertIsNone(run_sqlite_integrity_check("/nonexistent/db.sqlite3"))

    def test_directory_path_returns_none_without_connecting(self):
        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check(Path(__file__).resolve().parent))

        connect.assert_not_called()

    def test_blank_string_path_returns_none_without_connecting(self):
        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check(""))
            self.assertIsNone(run_sqlite_integrity_check("   "))

        connect.assert_not_called()

    def test_none_path_returns_none_without_connecting(self):
        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check(None))

        connect.assert_not_called()

    def test_overlong_resolved_path_returns_none_without_connecting(self):
        from pathlib import Path as StdPath

        class _ResolveLong(StdPath):
            def resolve(self, *args, **kwargs):
                return StdPath("Z" * 5000)

        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.Path",
            _ResolveLong,
        ), patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check("/tmp/db.sqlite3"))

        connect.assert_not_called()

    def test_bytes_path_returns_none_without_connecting(self):
        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check(b"/tmp/db.sqlite3"))

        connect.assert_not_called()

    def test_overlong_string_path_returns_none_without_connecting(self):
        from apps.siteconfig.repositories.database_recovery_repository import (
            _MAX_SQLITE_INTEGRITY_DB_PATH_LEN,
        )

        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(
                run_sqlite_integrity_check("x" * (_MAX_SQLITE_INTEGRITY_DB_PATH_LEN + 1))
            )

        connect.assert_not_called()

    def test_non_path_type_returns_none_without_connecting(self):
        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check(12345))

        connect.assert_not_called()

    def test_overlong_path_object_returns_none_without_connecting(self):
        from apps.siteconfig.repositories.database_recovery_repository import (
            _MAX_SQLITE_INTEGRITY_DB_PATH_LEN,
        )

        long_path = Path("p" * (_MAX_SQLITE_INTEGRITY_DB_PATH_LEN + 1))
        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check(long_path))

        connect.assert_not_called()

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

    def test_integrity_check_uses_read_only_sqlite_uri(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            fake_conn = MagicMock()
            fake_conn.cursor.return_value.execute.return_value.fetchone.return_value = ("ok",)

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ) as connect:
                self.assertEqual(run_sqlite_integrity_check(path), "ok")

            args, kwargs = connect.call_args
            self.assertTrue(args[0].startswith("file:"))
            self.assertIn("?mode=ro", args[0])
            self.assertEqual(
                kwargs,
                {"uri": True, "timeout": _SQLITE_INTEGRITY_CONNECT_TIMEOUT_SEC},
            )
            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)

    def test_integrity_check_result_clipped_when_overlong(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            long_msg = "e" * (_MAX_SQLITE_INTEGRITY_CHECK_RESULT_LEN + 100)
            fake_conn = MagicMock()
            fake_conn.cursor.return_value.execute.return_value.fetchone.return_value = (
                long_msg,
            )

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ):
                out = run_sqlite_integrity_check(path)

            self.assertEqual(len(out), _MAX_SQLITE_INTEGRITY_CHECK_RESULT_LEN)
            self.assertTrue(out.startswith("e"))
            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)
