"""
Tests for customers.repositories.schema_provisioning_repository (§2.4 raw SQL wrap).
Non-PG: schema_exists returns False, create_schema_if_not_exists no-ops. Empty name no-ops.
"""

import unittest
from unittest.mock import Mock, patch

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

    def test_schema_exists_pg_delegates_to_django_tenants(self):
        with patch.object(connection, "vendor", "postgresql"), patch(
            "django_tenants.utils.schema_exists", return_value=True
        ) as mock_schema_exists:
            self.assertTrue(schema_exists("test_schema"))

        mock_schema_exists.assert_called_once_with(
            "test_schema", database=connection.alias
        )

    def test_create_schema_if_not_exists_empty_no_op(self):
        create_schema_if_not_exists("")
        create_schema_if_not_exists("   ")

    def test_create_schema_if_not_exists_non_pg_no_op(self):
        with patch.object(connection, "vendor", "sqlite"):
            create_schema_if_not_exists("test_schema")

    def test_create_schema_if_not_exists_pg_delegates_to_client_create_schema(self):
        client = Mock()
        queryset = Mock()
        queryset.first.return_value = client

        with patch.object(connection, "vendor", "postgresql"), patch(
            "apps.customers.models.Client.objects.filter", return_value=queryset
        ) as mock_filter:
            create_schema_if_not_exists("test_schema")

        mock_filter.assert_called_once_with(schema_name="test_schema")
        client.create_schema.assert_called_once_with(check_if_exists=True, verbosity=0)

    def test_create_schema_if_not_exists_pg_no_op_when_client_missing(self):
        queryset = Mock()
        queryset.first.return_value = None

        with patch.object(connection, "vendor", "postgresql"), patch(
            "apps.customers.models.Client.objects.filter", return_value=queryset
        ) as mock_filter:
            create_schema_if_not_exists("test_schema")

        mock_filter.assert_called_once_with(schema_name="test_schema")
