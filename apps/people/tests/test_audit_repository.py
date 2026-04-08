"""
Tests for people.repositories.audit_repository (§2.4 raw SQL in repository).
Non-PG: all functions no-op. PG: used by attach_audit_triggers and revoke_audit_log_permissions.
"""

import unittest
from unittest.mock import MagicMock, patch

from django.db import connection


class TestAuditRepository(unittest.TestCase):
    """Audit repository no-ops on non-PostgreSQL."""

    def test_set_search_path_non_pg_no_op(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            set_search_path(cursor, "public")
            cursor.execute.assert_not_called()

    def test_set_search_path_pg_uses_set_local(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            set_search_path(cursor, "tenant_a")

        cursor.execute.assert_called_once_with(
            "SET LOCAL search_path TO %s", ["tenant_a"]
        )

    def test_set_search_path_pg_rejects_blank_schema_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                set_search_path(cursor, "   ")

        cursor.execute.assert_not_called()

    def test_set_search_path_pg_rejects_qualified_schema_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                set_search_path(cursor, "tenant_a.public")

        cursor.execute.assert_not_called()

    def test_set_search_path_pg_rejects_schema_name_over_pg_limit(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                set_search_path(cursor, "x" * 64)

        cursor.execute.assert_not_called()

    def test_set_search_path_pg_rejects_non_identifier_schema_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                set_search_path(cursor, "tenant-one")

        cursor.execute.assert_not_called()

    def test_set_search_path_pg_rejects_bool_schema_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                set_search_path(cursor, True)
            with self.assertRaises(ValueError):
                set_search_path(cursor, False)

        cursor.execute.assert_not_called()

    def test_set_search_path_pg_rejects_dict_schema_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                set_search_path(cursor, {"name": "tenant_a"})

        cursor.execute.assert_not_called()

    def test_set_search_path_pg_rejects_binary_buffer_schema_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import set_search_path

            cursor = MagicMock()
            for bad in (b"tenant_a", bytearray(b"tenant_a"), memoryview(b"tenant_a")):
                with self.assertRaises(ValueError):
                    set_search_path(cursor, bad)

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_blank_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import drop_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                drop_audit_trigger(cursor, "   ")

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_qualified_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import drop_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                drop_audit_trigger(cursor, "tenant_a.people_studentprofile")

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_bool_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import drop_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                drop_audit_trigger(cursor, True)

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_dict_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import drop_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                drop_audit_trigger(cursor, {"rel": "people_studentprofile"})

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_binary_buffer_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import drop_audit_trigger

            cursor = MagicMock()
            for bad in (
                b"people_studentprofile",
                bytearray(b"people_studentprofile"),
                memoryview(b"people_studentprofile"),
            ):
                with self.assertRaises(ValueError):
                    drop_audit_trigger(cursor, bad)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_blank_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                create_audit_trigger(cursor, "   ")

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_qualified_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                create_audit_trigger(cursor, "tenant_a.people_studentprofile")

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_non_identifier_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                create_audit_trigger(cursor, "people-bad")

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_bool_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                create_audit_trigger(cursor, True)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_dict_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                create_audit_trigger(cursor, {"rel": "people_studentprofile"})

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_binary_buffer_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            for bad in (
                b"people_studentprofile",
                bytearray(b"people_studentprofile"),
                memoryview(b"people_studentprofile"),
            ):
                with self.assertRaises(ValueError):
                    create_audit_trigger(cursor, bad)

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_table_name_over_pg_limit(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import drop_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                drop_audit_trigger(cursor, "a" * 64)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_rejects_table_name_over_audit_trigger_identifier_limit(
        self,
    ):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                create_audit_trigger(cursor, "x" * 58)

        cursor.execute.assert_not_called()

    def test_drop_audit_trigger_pg_rejects_table_name_over_audit_trigger_identifier_limit(
        self,
    ):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import drop_audit_trigger

            cursor = MagicMock()
            with self.assertRaises(ValueError):
                drop_audit_trigger(cursor, "y" * 58)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_pg_accepts_valid_table_name(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            create_audit_trigger(cursor, "people_studentprofile")

        cursor.execute.assert_called_once()

    def test_create_audit_trigger_pg_accepts_max_table_name_for_trigger_prefix(self):
        name = "m" * 57
        with patch.object(connection, "vendor", "postgresql"):
            from apps.people.repositories.audit_repository import create_audit_trigger

            cursor = MagicMock()
            create_audit_trigger(cursor, name)

        cursor.execute.assert_called_once()

    def test_create_audit_trigger_function_non_pg_no_op(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.people.repositories.audit_repository import (
                create_audit_trigger_function,
            )

            cursor = MagicMock()
            create_audit_trigger_function(cursor)
            cursor.execute.assert_not_called()

    def test_revoke_audit_log_mutations_non_pg_no_op(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.people.repositories.audit_repository import (
                revoke_audit_log_mutations,
            )

            cursor = MagicMock()
            revoke_audit_log_mutations(cursor)
            cursor.execute.assert_not_called()

    def test_create_audit_trigger_function_rejects_invalid_redact_keys_entry(self):
        from apps.people.repositories import audit_repository
        from apps.people.repositories.audit_repository import create_audit_trigger_function

        cursor = MagicMock()
        bad_keys = list(audit_repository.REDACT_KEYS) + ["invalid-hyphen"]
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(audit_repository, "REDACT_KEYS", bad_keys),
        ):
            with self.assertRaises(ValueError):
                create_audit_trigger_function(cursor)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_function_rejects_excessive_redact_keys_count(self):
        from apps.people.repositories import audit_repository
        from apps.people.repositories.audit_repository import create_audit_trigger_function

        cursor = MagicMock()
        many_keys = [f"k{i}" for i in range(65)]
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(audit_repository, "REDACT_KEYS", many_keys),
        ):
            with self.assertRaises(ValueError):
                create_audit_trigger_function(cursor)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_function_rejects_unsized_redact_keys_iterable(self):
        from apps.people.repositories import audit_repository
        from apps.people.repositories.audit_repository import create_audit_trigger_function

        class BrokenSizedIterable:
            def __len__(self):
                raise RuntimeError("len failed")

            def __iter__(self):
                return iter(["token"])

        cursor = MagicMock()
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(audit_repository, "REDACT_KEYS", BrokenSizedIterable()),
        ):
            with self.assertRaises(ValueError):
                create_audit_trigger_function(cursor)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_function_rejects_duplicate_redact_keys(self):
        from apps.people.repositories import audit_repository
        from apps.people.repositories.audit_repository import create_audit_trigger_function

        cursor = MagicMock()
        dup_keys = list(audit_repository.REDACT_KEYS) + ["token"]
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(audit_repository, "REDACT_KEYS", dup_keys),
        ):
            with self.assertRaises(ValueError):
                create_audit_trigger_function(cursor)

        cursor.execute.assert_not_called()

    def test_create_audit_trigger_function_rejects_redact_keys_iteration_failure(self):
        from apps.people.repositories import audit_repository
        from apps.people.repositories.audit_repository import create_audit_trigger_function

        class BrokenIterable:
            def __len__(self):
                return 1

            def __iter__(self):
                raise RuntimeError("iter failed")

        cursor = MagicMock()
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(audit_repository, "REDACT_KEYS", BrokenIterable()),
        ):
            with self.assertRaises(ValueError):
                create_audit_trigger_function(cursor)

        cursor.execute.assert_not_called()

    def test_audit_trigger_sql_matches_tenant_audit_log_contract(self):
        """Regression: trigger INSERT must use real PG column names and NOT NULL-safe values."""
        from apps.people.repositories.audit_repository import create_audit_trigger_function

        cursor = MagicMock()
        with patch.object(connection, "vendor", "postgresql"):
            create_audit_trigger_function(cursor)
        assert cursor.execute.called
        sql = cursor.execute.call_args[0][0]
        self.assertIn("changed_by_id", sql)
        self.assertNotIn("changed_by)", sql)
        self.assertNotIn(", changed_by\n", sql)
        self.assertIn("correlation_id", sql)
        self.assertIn("request_meta", sql)
        self.assertIn("'{}'::jsonb", sql)
