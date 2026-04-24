import unittest
from unittest.mock import MagicMock, patch

from django.db import connection

from apps.people.repositories import audit_repository
from apps.people.repositories.audit_repository import (
    _redact_keys_sql_array_literal,
    create_audit_trigger,
    create_audit_trigger_function,
    drop_audit_trigger,
    set_search_path,
)


class TestAuditRepositoryHelperGuards(unittest.TestCase):
    def test_set_search_path_pg_strips_surrounding_whitespace(self):
        with patch.object(connection, "vendor", "postgresql"):
            cursor = MagicMock()
            set_search_path(cursor, " tenant_a ")

        cursor.execute.assert_called_once_with(
            "SET LOCAL search_path TO %s",
            ["tenant_a"],
        )

    def test_set_search_path_pg_rejects_numeric_schema_name_without_sql(self):
        with patch.object(connection, "vendor", "postgresql"):
            cursor = MagicMock()
            with self.assertRaises(ValueError):
                set_search_path(cursor, 123)

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_numeric_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            cursor = MagicMock()
            with self.assertRaises(ValueError):
                drop_audit_trigger(cursor, 123)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_numeric_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            cursor = MagicMock()
            with self.assertRaises(ValueError):
                create_audit_trigger(cursor, 123)

        cursor.execute.assert_not_called()

    def test_redact_keys_sql_array_literal_accepts_empty_iterable(self):
        with patch.object(audit_repository, "REDACT_KEYS", []):
            self.assertEqual(_redact_keys_sql_array_literal(), "ARRAY[]::text[]")

    def test_create_audit_trigger_function_rejects_boolean_redact_key_entry(self):
        cursor = MagicMock()
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(audit_repository, "REDACT_KEYS", ["token", True]),
        ):
            with self.assertRaises(ValueError):
                create_audit_trigger_function(cursor)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_function_rejects_binary_redact_key_entry(self):
        cursor = MagicMock()
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(audit_repository, "REDACT_KEYS", ["token", b"secret"]),
        ):
            with self.assertRaises(ValueError):
                create_audit_trigger_function(cursor)

        cursor.execute.assert_not_called()
