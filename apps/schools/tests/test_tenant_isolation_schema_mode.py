"""
Schema-per-tenant isolation: in tenant A context, only A data is visible.
Requires PostgreSQL and USE_DJANGO_TENANTS=True. Tag: tenants_schema.
"""

import unittest

from django.db import connection
from django.db.utils import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
)
from django.test import TestCase, override_settings, tag


@tag("tenants_schema")
@unittest.skipIf(
    connection.vendor != "postgresql", "Schema-mode isolation tests require PostgreSQL"
)
@override_settings(USE_DJANGO_TENANTS=True)
class TenantIsolationSchemaModeTests(TestCase):
    """With schema-per-tenant, queries in tenant A must not see tenant B data."""

    def setUp(self):
        try:
            from apps.customers.models import Client, Domain
        except ImportError:
            self.skipTest("customers tenant models not available")
        self.Client = Client
        self.Domain = Domain
        self.client_a = Client.objects.create(schema_name="tenant_a", name="Tenant A")
        self.client_b = Client.objects.create(schema_name="tenant_b", name="Tenant B")
        Domain.objects.create(
            domain="tenant-a.test.com", tenant=self.client_a, is_primary=True
        )
        Domain.objects.create(
            domain="tenant-b.test.com", tenant=self.client_b, is_primary=True
        )

    def tearDown(self):
        _teardown_delete_errors = (
            DatabaseError,
            IntegrityError,
            OperationalError,
            ProgrammingError,
        )
        for attr in ("client_b", "client_a"):
            c = getattr(self, attr, None)
            if c is not None:
                try:
                    c.delete()
                except _teardown_delete_errors:
                    pass

    def test_tenant_context_isolates_data(self):
        from django_tenants.utils import tenant_context
        from apps.schools.models import School

        with tenant_context(self.client_a):
            school_a = School.objects.create(
                name="School A", slug="school-a", subdomain="school-a", is_active=True
            )
        with tenant_context(self.client_b):
            school_b = School.objects.create(
                name="School B", slug="school-b", subdomain="school-b", is_active=True
            )
        with tenant_context(self.client_a):
            current_ids = list(School.objects.values_list("id", flat=True))
            self.assertIn(school_a.id, current_ids)
            self.assertNotIn(school_b.id, current_ids)
        with tenant_context(self.client_b):
            current_ids = list(School.objects.values_list("id", flat=True))
            self.assertIn(school_b.id, current_ids)
            self.assertNotIn(school_a.id, current_ids)
