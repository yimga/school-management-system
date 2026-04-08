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

    def test_schema_exists_rejects_non_string_values_without_delegating(self):
        with patch.object(connection, "vendor", "postgresql"), patch(
            "django_tenants.utils.schema_exists"
        ) as mock_schema_exists:
            self.assertFalse(schema_exists(True))
            self.assertFalse(schema_exists({"schema_name": "tenant_a"}))
            self.assertFalse(schema_exists(b"tenant_a"))

        mock_schema_exists.assert_not_called()

    def test_schema_exists_rejects_string_subclass_strip_failure_without_delegating(
        self,
    ):
        class BadStripStr(str):
            def strip(self, chars=None):
                raise RuntimeError("strip failed")

        with patch.object(connection, "vendor", "postgresql"), patch(
            "django_tenants.utils.schema_exists"
        ) as mock_schema_exists:
            self.assertFalse(schema_exists(BadStripStr("tenant_a")))

        mock_schema_exists.assert_not_called()

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

    def test_schema_exists_bad_bool_result_returns_false(self):
        class BadBool:
            def __bool__(self):
                raise RuntimeError("bool failed")

        with patch.object(connection, "vendor", "postgresql"), patch(
            "django_tenants.utils.schema_exists", return_value=BadBool()
        ) as mock_schema_exists:
            self.assertFalse(schema_exists("test_schema"))

        mock_schema_exists.assert_called_once_with(
            "test_schema", database=connection.alias
        )

    def test_schema_exists_rejects_malformed_schema_name_without_delegating(self):
        with patch.object(connection, "vendor", "postgresql"), patch(
            "django_tenants.utils.schema_exists"
        ) as mock_schema_exists:
            self.assertFalse(schema_exists("tenant-a"))
            self.assertFalse(schema_exists("tenant_a.public"))
            self.assertFalse(schema_exists("x" * 64))

        mock_schema_exists.assert_not_called()

    def test_create_schema_if_not_exists_empty_no_op(self):
        create_schema_if_not_exists("")
        create_schema_if_not_exists("   ")

    def test_create_schema_if_not_exists_rejects_non_string_values_without_querying(
        self,
    ):
        with patch.object(connection, "vendor", "postgresql"), patch(
            "apps.customers.models.Client.objects.filter"
        ) as mock_filter:
            create_schema_if_not_exists(True)
            create_schema_if_not_exists({"schema_name": "tenant_a"})
            create_schema_if_not_exists(memoryview(b"tenant_a"))

        mock_filter.assert_not_called()

    def test_create_schema_if_not_exists_rejects_string_subclass_strip_failure_without_querying(
        self,
    ):
        class BadStripStr(str):
            def strip(self, chars=None):
                raise RuntimeError("strip failed")

        with patch.object(connection, "vendor", "postgresql"), patch(
            "apps.customers.models.Client.objects.filter"
        ) as mock_filter:
            create_schema_if_not_exists(BadStripStr("tenant_a"))

        mock_filter.assert_not_called()

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

    def test_create_schema_if_not_exists_rejects_malformed_schema_name_without_querying(
        self,
    ):
        with patch.object(connection, "vendor", "postgresql"), patch(
            "apps.customers.models.Client.objects.filter"
        ) as mock_filter:
            create_schema_if_not_exists("tenant-a")
            create_schema_if_not_exists("tenant_a.public")
            create_schema_if_not_exists("x" * 64)

        mock_filter.assert_not_called()

    def test_create_schema_if_not_exists_pg_no_op_when_client_missing(self):
        queryset = Mock()
        queryset.first.return_value = None

        with patch.object(connection, "vendor", "postgresql"), patch(
            "apps.customers.models.Client.objects.filter", return_value=queryset
        ) as mock_filter:
            create_schema_if_not_exists("test_schema")

        mock_filter.assert_called_once_with(schema_name="test_schema")
