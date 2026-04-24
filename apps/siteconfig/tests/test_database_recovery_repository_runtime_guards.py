import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.siteconfig.repositories.database_recovery_repository import (
    run_sqlite_integrity_check,
)


class TestDatabaseRecoveryRepositoryRuntimeGuards(unittest.TestCase):
    def test_resolve_value_error_returns_none_without_connecting(self):
        from pathlib import Path as StdPath

        class _ResolveValueError(StdPath):
            def resolve(self, *args, **kwargs):
                raise ValueError("bad path")

        with patch(
            "apps.siteconfig.repositories.database_recovery_repository.Path",
            _ResolveValueError,
        ), patch(
            "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect"
        ) as connect:
            self.assertIsNone(run_sqlite_integrity_check("/tmp/db.sqlite3"))

        connect.assert_not_called()

    def test_integrity_check_empty_row_returns_none_and_closes_connection(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            fake_conn = MagicMock()
            fake_conn.cursor.return_value.execute.return_value.fetchone.return_value = ()

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ):
                self.assertIsNone(run_sqlite_integrity_check(path))

            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)

    def test_integrity_check_execute_sqlite_error_returns_none_and_closes_connection(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            import sqlite3

            fake_conn = MagicMock()
            fake_conn.cursor.return_value.execute.side_effect = sqlite3.OperationalError(
                "broken"
            )

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ):
                self.assertIsNone(run_sqlite_integrity_check(path))

            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)

    def test_integrity_check_execute_os_error_returns_none_and_closes_connection(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            fake_conn = MagicMock()
            fake_conn.cursor.return_value.execute.side_effect = OSError("disk error")

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ):
                self.assertIsNone(run_sqlite_integrity_check(path))

            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)

    def test_integrity_check_fetchone_none_returns_none_and_closes_connection(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            fake_conn = MagicMock()
            fake_conn.cursor.return_value.execute.return_value.fetchone.return_value = None

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ):
                self.assertIsNone(run_sqlite_integrity_check(path))

            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)

    def test_integrity_check_execute_database_error_returns_none_and_closes_connection(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            import sqlite3

            fake_conn = MagicMock()
            fake_conn.cursor.return_value.execute.side_effect = sqlite3.DatabaseError(
                "malformed"
            )

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ):
                self.assertIsNone(run_sqlite_integrity_check(path))

            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)

    def test_integrity_check_cursor_factory_raises_returns_none_and_closes_connection(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            path = Path(f.name)
        try:
            import sqlite3

            fake_conn = MagicMock()
            fake_conn.cursor.side_effect = sqlite3.OperationalError("cursor failed")

            with patch(
                "apps.siteconfig.repositories.database_recovery_repository.sqlite3.connect",
                return_value=fake_conn,
            ):
                self.assertIsNone(run_sqlite_integrity_check(path))

            fake_conn.close.assert_called_once_with()
        finally:
            path.unlink(missing_ok=True)
