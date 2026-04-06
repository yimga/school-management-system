"""
Tests for schools.repositories.health_repository (§2.4 raw SQL in repository).
Non-PG: returns []. PG: structure and tenant scoping (schema_name) verified.
"""

import unittest
from unittest.mock import MagicMock, patch

from django.db import connection


class TestHealthRepository(unittest.TestCase):
    """Health repository returns empty on non-PG; structure on PG."""

    def test_get_top_tables_by_size_non_pg_returns_empty(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(get_top_tables_by_size(10), [])

    def test_get_global_health_stats_non_pg_returns_empty(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(get_global_health_stats(), [])

    def test_get_global_health_stats_applies_schema_row_limit(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("pretty_size",),
            ("raw_size",),
            ("table_count",),
        ]
        fake_cursor.fetchall.return_value = []
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        with patch.object(connection, "vendor", "postgresql"), patch.object(
            connection, "cursor", return_value=fake_context
        ):
            from apps.schools.repositories import health_repository
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            cap = health_repository._HEALTH_GLOBAL_SCHEMA_STATS_MAX_LIMIT
            self.assertEqual(get_global_health_stats(), [])

        sql, params = fake_cursor.execute.call_args.args
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(params, [cap])

    def test_check_table_exists_non_pg_returns_false(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("public.schools_school"))

    def test_check_table_exists_rejects_bool_qualified_table_without_introspection(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists(True))
            self.assertFalse(check_table_exists(False))

        table_names.assert_not_called()

    def test_check_table_exists_rejects_bytes_qualified_table_without_introspection(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists(b"public.schools_school"))

        table_names.assert_not_called()

    def test_check_table_exists_rejects_bytearray_qualified_table_without_introspection(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(
                check_table_exists(bytearray(b"public.schools_school")),
            )

        table_names.assert_not_called()

    def test_check_table_exists_uses_visible_table_names(self):
        with patch.object(connection, "vendor", "postgresql"), patch.object(
            connection, "schema_name", "tenant_a", create=True
        ), patch.object(
            connection.introspection,
            "table_names",
            return_value=["schools_school", "people_studentprofile"],
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertTrue(check_table_exists("public.schools_school"))
            self.assertTrue(check_table_exists("tenant_a.people_studentprofile"))
            self.assertFalse(check_table_exists("other_schema.people_studentprofile"))

    def test_check_table_exists_rejects_blank_identifier_without_introspection(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("   "))

        table_names.assert_not_called()

    def test_check_table_exists_rejects_multi_part_identifier_without_introspection(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("public.people.studentprofile"))

        table_names.assert_not_called()

    def test_check_table_exists_rejects_non_identifier_table_without_introspection(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "schema_name", "tenant_a", create=True),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("public.schools-school"))

        table_names.assert_not_called()

    def test_check_table_exists_rejects_overlong_table_without_introspection(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "schema_name", "tenant_a", create=True),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("public." + "t" * 64))

        table_names.assert_not_called()

    def test_check_table_exists_rejects_unqualified_non_identifier_without_introspection(
        self,
    ):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection.introspection, "table_names") as table_names,
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("schools-school"))

        table_names.assert_not_called()

    def test_get_top_tables_by_size_filters_to_requested_schema(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("table_name",),
            ("total_pretty",),
            ("raw_size",),
            ("row_count",),
        ]
        fake_cursor.fetchall.return_value = [
            ("tenant_a", "people_studentprofile", "64 kB", 65536, 42)
        ]
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        with patch.object(connection, "vendor", "postgresql"), patch.object(
            connection, "cursor", return_value=fake_context
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            result = get_top_tables_by_size(limit=7, schema_name="tenant_a")

        self.assertEqual(
            result,
            [
                {
                    "schema_name": "tenant_a",
                    "table_name": "people_studentprofile",
                    "total_pretty": "64 kB",
                    "raw_size": 65536,
                    "row_count": 42,
                }
            ],
        )
        self.assertEqual(fake_cursor.execute.call_count, 1)
        sql, params = fake_cursor.execute.call_args.args
        self.assertIn("AND schemaname = %s", sql)
        self.assertEqual(params, ["tenant_a", 7])

    def test_get_top_tables_by_size_caps_excessive_limit(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("table_name",),
            ("total_pretty",),
            ("raw_size",),
            ("row_count",),
        ]
        fake_cursor.fetchall.return_value = []
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        with patch.object(connection, "vendor", "postgresql"), patch.object(
            connection, "cursor", return_value=fake_context
        ):
            from apps.schools.repositories import health_repository
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            cap = health_repository._HEALTH_TOP_TABLES_MAX_LIMIT
            self.assertEqual(
                get_top_tables_by_size(limit=999_999, schema_name="tenant_a"), []
            )

        _sql, params = fake_cursor.execute.call_args.args
        self.assertEqual(params, ["tenant_a", cap])

    def test_get_top_tables_by_size_caps_excessive_limit_without_schema_filter(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("table_name",),
            ("total_pretty",),
            ("raw_size",),
            ("row_count",),
        ]
        fake_cursor.fetchall.return_value = []
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        with patch.object(connection, "vendor", "postgresql"), patch.object(
            connection, "cursor", return_value=fake_context
        ):
            from apps.schools.repositories import health_repository
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            cap = health_repository._HEALTH_TOP_TABLES_MAX_LIMIT
            self.assertEqual(get_top_tables_by_size(limit=50_000), [])

        _sql, params = fake_cursor.execute.call_args.args
        self.assertEqual(params, [cap])

    def test_get_top_tables_by_size_does_not_set_search_path(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("table_name",),
            ("total_pretty",),
            ("raw_size",),
            ("row_count",),
        ]
        fake_cursor.fetchall.return_value = []
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        with patch.object(connection, "vendor", "postgresql"), patch.object(
            connection, "cursor", return_value=fake_context
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(get_top_tables_by_size(limit=5, schema_name="tenant_a"), [])

        executed_sql, params = fake_cursor.execute.call_args.args
        self.assertNotIn("SET search_path", executed_sql)
        self.assertEqual(params, ["tenant_a", 5])

    def test_get_top_tables_by_size_rejects_blank_schema_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(get_top_tables_by_size(limit=5, schema_name="   "), [])

        cursor.assert_not_called()

    def test_get_top_tables_by_size_rejects_malformed_schema_name_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(
                get_top_tables_by_size(limit=5, schema_name="tenant-bad"),
                [],
            )
            self.assertEqual(
                get_top_tables_by_size(limit=5, schema_name="x" * 64),
                [],
            )

        cursor.assert_not_called()

    def test_get_top_tables_by_size_rejects_bool_limit_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(get_top_tables_by_size(limit=True), [])
            self.assertEqual(get_top_tables_by_size(limit=False), [])

        cursor.assert_not_called()

    def test_get_top_tables_by_size_rejects_bytes_limit_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(get_top_tables_by_size(limit=b"10"), [])

        cursor.assert_not_called()

    def test_get_top_tables_by_size_rejects_bool_schema_name_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(get_top_tables_by_size(limit=5, schema_name=True), [])
            self.assertEqual(get_top_tables_by_size(limit=5, schema_name=False), [])

        cursor.assert_not_called()

    def test_get_top_tables_by_size_rejects_bytes_schema_name_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(
                get_top_tables_by_size(limit=5, schema_name=b"tenant_a"),
                [],
            )

        cursor.assert_not_called()

    def test_get_top_tables_by_size_rejects_non_positive_limit_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import (
                get_top_tables_by_size,
            )

            self.assertEqual(get_top_tables_by_size(limit=0, schema_name="tenant_a"), [])

        cursor.assert_not_called()

    def test_count_table_rows_non_pg_returns_zero(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "schools_school"), 0)

    def test_count_table_rows_rejects_bool_schema_or_table_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows(True, "schools_school"), -1)
            self.assertEqual(count_table_rows("public", False), -1)

        cursor.assert_not_called()

    def test_count_table_rows_rejects_bytes_schema_or_table_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows(b"public", "schools_school"), -1)
            self.assertEqual(count_table_rows("public", b"schools_school"), -1)

        cursor.assert_not_called()

    def test_count_table_rows_rejects_blank_schema_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("   ", "schools_school"), -1)

        cursor.assert_not_called()

    def test_count_table_rows_rejects_blank_table_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "   "), -1)

        cursor.assert_not_called()

    def test_count_table_rows_rejects_qualified_schema_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("tenant.public", "schools_school"), -1)

        cursor.assert_not_called()

    def test_count_table_rows_rejects_qualified_table_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "schools.school"), -1)

        cursor.assert_not_called()

    def test_count_table_rows_rejects_non_identifier_table_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "schools-school"), -1)

        cursor.assert_not_called()

    def test_count_table_rows_rejects_overlong_identifier_without_sql(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor") as cursor,
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("a" * 64, "schools_school"), -1)

        cursor.assert_not_called()

    def test_count_table_rows_valid_identifiers_execute_count(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = (42,)
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_cursor
        fake_context.__exit__.return_value = False

        with patch.object(connection, "vendor", "postgresql"), patch.object(
            connection, "cursor", return_value=fake_context
        ), patch.object(connection.ops, "quote_name", side_effect=lambda n: f'"{n}"'):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "schools_school"), 42)

        fake_cursor.execute.assert_called_once()
        sql, = fake_cursor.execute.call_args[0]
        self.assertIn("COUNT(*)", sql)
        self.assertIn('"public"', sql)
        self.assertIn('"schools_school"', sql)

    def test_health_utils_delegates_to_repository(self):
        """health_utils is thin wrapper; same result as repository on non-PG."""
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.health_utils import (
                get_top_tables_by_size,
                get_global_health_stats,
            )

            self.assertEqual(get_top_tables_by_size(5), [])
            self.assertEqual(get_global_health_stats(), [])
