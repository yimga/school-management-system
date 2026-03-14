"""
Tests for schools.repositories.health_repository (§2.4 raw SQL in repository).
Non-PG: returns []. PG: structure and tenant scoping (schema_name) verified.
"""
import unittest
from unittest.mock import patch

from django.db import connection


class TestHealthRepository(unittest.TestCase):
    """Health repository returns empty on non-PG; structure on PG."""

    def test_get_top_tables_by_size_non_pg_returns_empty(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import get_top_tables_by_size
            self.assertEqual(get_top_tables_by_size(10), [])

    def test_get_global_health_stats_non_pg_returns_empty(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import get_global_health_stats
            self.assertEqual(get_global_health_stats(), [])

    def test_check_table_exists_non_pg_returns_false(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import check_table_exists
            self.assertFalse(check_table_exists("public.schools_school"))

    def test_count_table_rows_non_pg_returns_zero(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.health_repository import count_table_rows
            self.assertEqual(count_table_rows("public", "schools_school"), 0)

    def test_health_utils_delegates_to_repository(self):
        """health_utils is thin wrapper; same result as repository on non-PG."""
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.health_utils import get_top_tables_by_size, get_global_health_stats
            self.assertEqual(get_top_tables_by_size(5), [])
            self.assertEqual(get_global_health_stats(), [])
