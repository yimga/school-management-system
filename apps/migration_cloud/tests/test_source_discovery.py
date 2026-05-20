"""Discovery service tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import (
    DiscoveryRunStatus,
    MigrationConnectorProfile,
)
from apps.migration_cloud.services.connector_credentials import (
    create_source_connection,
    verify_source_authorization,
)
from apps.migration_cloud.services.connector_discovery import run_source_discovery

User = get_user_model()


class SourceDiscoveryTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Discovery School", slug="disc-test", subdomain="disc-test"
        )
        self.user = User.objects.create_user(username="disc_user", password="unused")
        self.profile, _ = MigrationConnectorProfile.objects.get_or_create(
            key="generic_csv_export",
            defaults={"display_name": "Generic CSV", "certification_status": "production_ready"},
        )

    def _verified_connection(self):
        conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        conn.authorization_confirmed = True
        conn.terms_acknowledged = True
        conn.save()
        verify_source_authorization(conn)
        conn.refresh_from_db()
        return conn

    def test_discovery_requires_verified_connection(self):
        conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        with self.assertRaises(ValueError):
            run_source_discovery(connection=conn, started_by=self.user)

    def test_discovery_records_counts(self):
        conn = self._verified_connection()
        run = run_source_discovery(connection=conn, started_by=self.user)
        self.assertEqual(run.status, DiscoveryRunStatus.COMPLETED)
        self.assertTrue(run.counts_by_entity)

    def test_discovery_tenant_scoped(self):
        conn = self._verified_connection()
        run = run_source_discovery(connection=conn, started_by=self.user)
        self.assertEqual(run.school_id, self.school.pk)
