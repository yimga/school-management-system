"""Driver errors on cursor.execute: debug log then re-raise (audit DDL; management commands handle)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

from apps.people.repositories.audit_repository import (
    create_audit_trigger,
    create_audit_trigger_function,
    drop_audit_trigger,
    revoke_audit_log_mutations,
    set_search_path,
)


class TestAuditRepositoryExecuteGuards(unittest.TestCase):
    def test_set_search_path_operational_error_reraises(self):
        cursor = MagicMock()
        cursor.execute.side_effect = OperationalError("boom")
        with patch.object(connection, "vendor", "postgresql"):
            with self.assertRaises(OperationalError):
                set_search_path(cursor, "tenant_a")
        cursor.execute.assert_called_once()

    def test_create_audit_trigger_function_operational_error_reraises(self):
        cursor = MagicMock()
        cursor.execute.side_effect = OperationalError("boom")
        with patch.object(connection, "vendor", "postgresql"):
            with self.assertRaises(OperationalError):
                create_audit_trigger_function(cursor)
        cursor.execute.assert_called_once()

    def test_drop_audit_trigger_operational_error_reraises(self):
        cursor = MagicMock()
        cursor.execute.side_effect = OperationalError("boom")
        with patch.object(connection, "vendor", "postgresql"):
            with self.assertRaises(OperationalError):
                drop_audit_trigger(cursor, "people_student")
        cursor.execute.assert_called_once()

    def test_create_audit_trigger_operational_error_reraises(self):
        cursor = MagicMock()
        cursor.execute.side_effect = OperationalError("boom")
        with patch.object(connection, "vendor", "postgresql"):
            with self.assertRaises(OperationalError):
                create_audit_trigger(cursor, "people_student")
        cursor.execute.assert_called_once()

    def test_revoke_audit_log_mutations_operational_error_reraises(self):
        cursor = MagicMock()
        cursor.execute.side_effect = OperationalError("boom")
        with patch.object(connection, "vendor", "postgresql"):
            with self.assertRaises(OperationalError):
                revoke_audit_log_mutations(cursor)
        cursor.execute.assert_called_once_with(
            "REVOKE UPDATE, DELETE ON audit_log FROM CURRENT_USER;"
        )

    def test_set_search_path_programming_error_reraises(self):
        cursor = MagicMock()
        cursor.execute.side_effect = ProgrammingError("syntax")
        with patch.object(connection, "vendor", "postgresql"):
            with self.assertRaises(ProgrammingError):
                set_search_path(cursor, "tenant_a")
        cursor.execute.assert_called_once()
