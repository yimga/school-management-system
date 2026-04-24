import unittest
from unittest.mock import MagicMock, patch

from django.db import connection
from django.db.utils import DatabaseError, OperationalError, ProgrammingError


class TestHealthRepositoryResultGuards(unittest.TestCase):
    def test_count_table_rows_operational_error_returns_negative_one(self):
        fake_cursor = MagicMock()
        fake_cursor.execute.side_effect = OperationalError("boom")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "schools_school"), -1)

    def test_count_table_rows_programming_error_returns_negative_one(self):
        fake_cursor = MagicMock()
        fake_cursor.execute.side_effect = ProgrammingError("bad sql")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "schools_school"), -1)

    def test_count_table_rows_database_error_returns_negative_one(self):
        fake_cursor = MagicMock()
        fake_cursor.execute.side_effect = DatabaseError("db down")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import count_table_rows

            self.assertEqual(count_table_rows("public", "schools_school"), -1)

    def test_check_table_exists_operational_error_returns_false(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "schema_name", "tenant_a", create=True),
            patch.object(
                connection.introspection,
                "table_names",
                side_effect=OperationalError("boom"),
            ),
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("public.schools_school"))

    def test_check_table_exists_programming_error_returns_false(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "schema_name", "tenant_a", create=True),
            patch.object(
                connection.introspection,
                "table_names",
                side_effect=ProgrammingError("bad introspection"),
            ),
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("tenant_a.people_studentprofile"))

    def test_check_table_exists_database_error_returns_false(self):
        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(
                connection.introspection,
                "table_names",
                side_effect=DatabaseError("db down"),
            ),
        ):
            from apps.schools.repositories.health_repository import check_table_exists

            self.assertFalse(check_table_exists("schools_school"))

    def test_get_top_tables_by_size_bad_description_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [None]
        fake_cursor.fetchall.return_value = [
            ("tenant_a", "people_studentprofile", "12 kB", 12288, 3)
        ]
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import get_top_tables_by_size

            self.assertEqual(
                get_top_tables_by_size(limit=1, schema_name="tenant_a"),
                [],
            )

        fake_cursor.execute.assert_called_once()

    def test_get_top_tables_by_size_fetchall_failure_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("table_name",),
            ("total_pretty",),
            ("raw_size",),
            ("row_count",),
        ]
        fake_cursor.fetchall.side_effect = RuntimeError("boom")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import get_top_tables_by_size

            self.assertEqual(
                get_top_tables_by_size(limit=1, schema_name="tenant_a"),
                [],
            )

        fake_cursor.execute.assert_called_once()

    def test_get_global_health_stats_returns_dict_rows_for_valid_results(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("pretty_size",),
            ("raw_size",),
            ("table_count",),
        ]
        fake_cursor.fetchall.return_value = [
            ("tenant_a", "12 kB", 12288, 3),
            ("public", "4 kB", 4096, 1),
        ]
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(
                get_global_health_stats(limit=2),
                [
                    {
                        "schema_name": "tenant_a",
                        "pretty_size": "12 kB",
                        "raw_size": 12288,
                        "table_count": 3,
                    },
                    {
                        "schema_name": "public",
                        "pretty_size": "4 kB",
                        "raw_size": 4096,
                        "table_count": 1,
                    },
                ],
            )

        fake_cursor.execute.assert_called_once()

    def test_get_global_health_stats_bad_description_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [None]
        fake_cursor.fetchall.return_value = [("tenant_a", "12 kB", 12288, 3)]
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(get_global_health_stats(limit=1), [])

        fake_cursor.execute.assert_called_once()

    def test_get_global_health_stats_short_description_entry_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [()]
        fake_cursor.fetchall.return_value = [("tenant_a", "12 kB", 12288, 3)]
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(get_global_health_stats(limit=1), [])

        fake_cursor.execute.assert_called_once()

    def test_get_global_health_stats_bad_result_row_returns_empty(self):
        class BadRow:
            def __iter__(self):
                raise RuntimeError("bad row")

        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("pretty_size",),
            ("raw_size",),
            ("table_count",),
        ]
        fake_cursor.fetchall.return_value = [BadRow()]
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(get_global_health_stats(limit=1), [])

        fake_cursor.execute.assert_called_once()

    def test_get_global_health_stats_fetchall_failure_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.description = [
            ("schema_name",),
            ("pretty_size",),
            ("raw_size",),
            ("table_count",),
        ]
        fake_cursor.fetchall.side_effect = RuntimeError("boom")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(get_global_health_stats(limit=1), [])

        fake_cursor.execute.assert_called_once()

    def test_get_top_tables_by_size_execute_error_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.execute.side_effect = OperationalError("execute failed")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import get_top_tables_by_size

            self.assertEqual(
                get_top_tables_by_size(limit=1, schema_name="tenant_a"),
                [],
            )

    def test_get_top_tables_by_size_cursor_context_error_returns_empty(self):
        fake_cm = MagicMock()
        fake_cm.__enter__.side_effect = DatabaseError("no cursor")
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import get_top_tables_by_size

            self.assertEqual(get_top_tables_by_size(limit=1), [])

    def test_get_global_health_stats_execute_error_returns_empty(self):
        fake_cursor = MagicMock()
        fake_cursor.execute.side_effect = ProgrammingError("bad catalog query")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_cursor
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(get_global_health_stats(limit=2), [])

    def test_get_global_health_stats_cursor_context_error_returns_empty(self):
        fake_cm = MagicMock()
        fake_cm.__enter__.side_effect = OperationalError("connection lost")
        fake_cm.__exit__.return_value = False

        with (
            patch.object(connection, "vendor", "postgresql"),
            patch.object(connection, "cursor", return_value=fake_cm),
        ):
            from apps.schools.repositories.health_repository import (
                get_global_health_stats,
            )

            self.assertEqual(get_global_health_stats(), [])
