"""Credential security tests for Migration Cloud connectors."""

from __future__ import annotations


from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import (
    CredentialStorageMode,
    MigrationConnectorProfile,
    MigrationSourceConnection,
    SourceConnectionStatus,
)
from apps.migration_cloud.services.connector_credentials import (
    create_source_connection,
    redact_connection_for_display,
    retrieve_source_credential_for_runtime,
    revoke_source_connection,
    store_source_credential_reference,
    verify_source_authorization,
)

User = get_user_model()


class SourceConnectionSecurityTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Connector Test School", slug="connector-test", subdomain="connector-test"
        )
        self.user = User.objects.create_user(username="connector_admin", password="unused-test-pw")
        self.profile, _ = MigrationConnectorProfile.objects.get_or_create(
            key="generic_csv_export",
            defaults={
                "display_name": "Generic CSV",
                "certification_status": "production_ready",
            },
        )

    def test_password_not_in_redacted_display(self):
        conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        store_source_credential_reference(conn, credential_payload={"password": "Secret123!"})
        display = redact_connection_for_display(conn)
        self.assertNotIn("Secret123!", str(display))
        self.assertNotIn("password", str(display).lower())

    def test_password_not_logged_on_store(self):
        conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="api_token",
        )
        with self.assertNoLogs("apps.migration_cloud.services.connector_credentials", level="DEBUG"):
            store_source_credential_reference(conn, credential_payload={"api_token": "tok_live_abc"})

    def test_connection_revoked_and_purged(self):
        conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="api_token",
            credential_storage_mode=CredentialStorageMode.MEMORY_ONLY,
        )
        store_source_credential_reference(conn, credential_payload={"api_token": "tok_live_abc"})
        self.assertIsNotNone(retrieve_source_credential_for_runtime(conn))
        revoke_source_connection(conn)
        conn.refresh_from_db()
        self.assertEqual(conn.status, SourceConnectionStatus.REVOKED)
        self.assertIsNone(retrieve_source_credential_for_runtime(conn))

    def test_tenant_scoped_connection(self):
        from apps.schools.models import School

        other = School.objects.create(name="Other", slug="other-conn", subdomain="other-conn")
        c1 = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://a.example.edu",
            connection_method="file_export",
        )
        create_source_connection(
            school=other,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://b.example.edu",
            connection_method="file_export",
        )
        # tenant-isolation-allow: connector-security-test-scoped-by-school-pk
        qs = MigrationSourceConnection.objects.filter(school=self.school)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.get().id, c1.id)

    def test_verify_requires_authorization(self):
        conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        ok, blockers = verify_source_authorization(conn)
        self.assertFalse(ok)
        self.assertIn("authorization_not_confirmed", blockers)
