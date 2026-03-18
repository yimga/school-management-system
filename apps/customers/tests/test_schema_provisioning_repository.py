"""
Tests for customers.repositories.schema_provisioning_repository (§2.4 raw SQL wrap).
Non-PG: schema_exists returns False, create_schema_if_not_exists no-ops. Empty name no-ops.
"""

import unittest
from unittest.mock import patch

from django.db import connection

from apps.customers.repositories.schema_provisioning_repository import (
    create_schema_if_not_exists,
    schema_exists,
)


class TestSchemaProvisioningRepository(unittest.TestCase):
    """Schema provisioning repository: no-op on non-PG and empty name."""

    def test_schema_exists_empty_returns_false(self):
        self.assertFalse(schema_exists(""))
        self.assertFalse(schema_exists("   "))

    def test_schema_exists_non_pg_returns_false(self):
        with patch.object(connection, "vendor", "sqlite"):
            self.assertFalse(schema_exists("test_schema"))

    def test_create_schema_if_not_exists_empty_no_op(self):
        create_schema_if_not_exists("")
        create_schema_if_not_exists("   ")

    def test_create_schema_if_not_exists_non_pg_no_op(self):
        with patch.object(connection, "vendor", "sqlite"):
            create_schema_if_not_exists("test_schema")
