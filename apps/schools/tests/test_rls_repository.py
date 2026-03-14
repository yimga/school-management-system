"""
Tests for schools.repositories.rls_repository (§2.4 raw SQL in repository).
Non-PG: returns {}. PG: used by verify_tenant_rls command.
"""
import unittest
from unittest.mock import patch

from django.db import connection


class TestRlsRepository(unittest.TestCase):
    """RLS repository returns empty dict on non-PG."""

    def test_get_tenant_rls_status_non_pg_returns_empty(self):
        with patch.object(connection, "vendor", "sqlite"):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status
            self.assertEqual(get_tenant_rls_status(["people_studentprofile"]), {})

    def test_get_tenant_rls_status_empty_list_returns_empty(self):
        with patch.object(connection, "vendor", "postgresql"):
            from apps.schools.repositories.rls_repository import get_tenant_rls_status
            self.assertEqual(get_tenant_rls_status([]), {})
