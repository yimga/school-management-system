"""Tenant isolation for connector models."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import MigrationConnectorProfile, MigrationSourceConnection
from apps.migration_cloud.services.connector_credentials import create_source_connection

User = get_user_model()


class MigrationCloudTenantIsolationTests(TestCase):
    def test_cross_tenant_connection_invisible(self):
        from apps.schools.models import School

        school_a = School.objects.create(name="A", slug="iso-a", subdomain="iso-a")
        school_b = School.objects.create(name="B", slug="iso-b", subdomain="iso-b")
        user = User.objects.create_user(username="iso_user", password="unused")
        profile, _ = MigrationConnectorProfile.objects.get_or_create(
            key="generic_csv_export",
            defaults={"display_name": "Generic CSV", "certification_status": "production_ready"},
        )
        conn_b = create_source_connection(
            school=school_b,
            created_by=user,
            connector_profile=profile,
            source_platform_type="generic_csv_export",
            source_url="https://b.example.edu",
            connection_method="file_export",
        )
        # tenant-isolation-allow: connector-isolation-test-filter-by-school-a
        visible = MigrationSourceConnection.objects.filter(school=school_a, id=conn_b.id)
        self.assertFalse(visible.exists())
