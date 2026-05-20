"""Rollback posture tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import ImportRunStatus, MigrationImportRun
from apps.migration_cloud.services.connector_rollback import rollback_preview

User = get_user_model()


class RollbackPostureTests(TestCase):
    def setUp(self):
        from apps.schools.models import School
        from apps.migration_cloud.models_connectors import MigrationConnectorProfile
        from apps.migration_cloud.services.connector_credentials import create_source_connection

        self.school = School.objects.create(
            name="Rollback School", slug="rb-test", subdomain="rb-test"
        )
        self.user = User.objects.create_user(username="rb_user", password="unused")
        profile, _ = MigrationConnectorProfile.objects.get_or_create(
            key="generic_csv_export",
            defaults={"display_name": "Generic CSV", "certification_status": "production_ready"},
        )
        self.conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        self.import_run = MigrationImportRun.objects.create(
            school=self.school,
            source_connection=self.conn,
            status=ImportRunStatus.COMPLETED,
            idempotency_key="rb-preview-key",
            rollback_snapshot_reference="preview:students:abc",
            created_counts={"students": 10},
        )

    def test_rollback_preview_exists(self):
        preview = rollback_preview(import_run=self.import_run, actor=self.user)
        self.assertIn("category", preview)
        self.assertTrue(preview.get("source_unchanged"))

    def test_rollback_audited(self):
        rollback_preview(import_run=self.import_run, actor=self.user)
        self.assertTrue(
            self.import_run.audit_events.filter(event_type="rollback_previewed").exists()
        )
