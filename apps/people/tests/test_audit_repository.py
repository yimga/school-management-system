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
