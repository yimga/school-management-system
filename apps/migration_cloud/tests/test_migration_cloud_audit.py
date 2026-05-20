"""Connector workflow audit tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import MigrationConnectorProfile
from apps.migration_cloud.services.connector_audit import record_connector_audit
from apps.migration_cloud.services.connector_credentials import create_source_connection

User = get_user_model()


class MigrationCloudAuditTests(TestCase):
    def test_audit_metadata_redacts_secrets(self):
        from apps.schools.models import School

        school = School.objects.create(
            name="Audit School", slug="audit-test", subdomain="audit-test"
        )
        user = User.objects.create_user(username="audit_user", password="unused")
        profile, _ = MigrationConnectorProfile.objects.get_or_create(
            key="generic_csv_export",
            defaults={"display_name": "Generic CSV", "certification_status": "production_ready"},
        )
        conn = create_source_connection(
            school=school,
            created_by=user,
            connector_profile=profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        event = record_connector_audit(
            school=school,
            actor=user,
            event_type="connection_created",
            source_connection=conn,
            metadata={"password": "must-not-persist", "result": "ok"},
        )
        self.assertNotIn("must-not-persist", str(event.metadata))
        self.assertNotIn("password", event.metadata)
