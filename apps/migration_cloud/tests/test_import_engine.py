"""Import engine tests."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import (
    ImportRunStatus,
    MigrationConnectorProfile,
    MigrationStagingBatch,
    StagingBatchStatus,
)
from apps.migration_cloud.services.connector_credentials import (
    create_source_connection,
    verify_source_authorization,
)
from apps.migration_cloud.services.connector_import import run_connector_import
from apps.migration_cloud.services.connector_mapping import confirm_mappings, suggest_field_mappings

User = get_user_model()


class ImportEngineTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Import School", slug="import-test", subdomain="import-test"
        )
        self.user = User.objects.create_user(username="import_user", password="unused")
        self.profile, _ = MigrationConnectorProfile.objects.get_or_create(
            key="generic_csv_export",
            defaults={"display_name": "Generic CSV", "certification_status": "production_ready"},
        )
        self.conn = create_source_connection(
            school=self.school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://sis.example.edu",
            connection_method="file_export",
        )
        self.conn.authorization_confirmed = True
        self.conn.terms_acknowledged = True
        self.conn.save()
        verify_source_authorization(self.conn)
        suggest_field_mappings(
            connection=self.conn,
            entity_type="students",
            source_fields=["admission_number", "first_name", "last_name"],
            actor=self.user,
        )
        confirm_mappings(connection=self.conn, entity_type="students", actor=self.user)
        self.batch = MigrationStagingBatch.objects.create(
            school=self.school,
            source_connection=self.conn,
            entity_type="students",
            raw_count=1,
            valid_count=1,
            staged_rows=[
                {
                    "admission_number": "IMP-001",
                    "first_name": "Import",
                    "last_name": "Student",
                }
            ],
            status=StagingBatchStatus.STAGED,
            data_quality_score=Decimal("95.00"),
        )

    def test_import_requires_authorization(self):
        from apps.schools.models import School

        other_school = School.objects.create(
            name="Other", slug="other-import", subdomain="other-import"
        )
        conn = create_source_connection(
            school=other_school,
            created_by=self.user,
            connector_profile=self.profile,
            source_platform_type="generic_csv_export",
            source_url="https://other.example.edu",
            connection_method="file_export",
        )
        batch = MigrationStagingBatch.objects.create(
            school=other_school,
            source_connection=conn,
            entity_type="students",
            data_quality_score=Decimal("95.00"),
        )
        with self.assertRaises(ValueError):
            run_connector_import(
                connection=conn,
                staging_batch=batch,
                started_by=self.user,
            )

    def test_import_idempotency(self):
        key = "test-idem-key-1"
        run1 = run_connector_import(
            connection=self.conn,
            staging_batch=self.batch,
            started_by=self.user,
            idempotency_key=key,
        )
        run2 = run_connector_import(
            connection=self.conn,
            staging_batch=self.batch,
            started_by=self.user,
            idempotency_key=key,
        )
        self.assertEqual(run1.id, run2.id)

    def test_import_emits_audit(self):
        run = run_connector_import(
            connection=self.conn,
            staging_batch=self.batch,
            started_by=self.user,
            idempotency_key="audit-import-key",
            dry_run_apply=True,
        )
        self.assertEqual(run.status, ImportRunStatus.COMPLETED)
        self.assertTrue(
            self.conn.audit_events.filter(event_type="import_completed").exists()
        )
        self.assertIsNotNone(run.bundle_id)
        self.assertIn("pipeline", run.audit_summary)

    def test_import_runs_orchestrator_pipeline(self):
        run = run_connector_import(
            connection=self.conn,
            staging_batch=self.batch,
            started_by=self.user,
            idempotency_key="pipeline-import-key",
            dry_run_apply=True,
        )
        pipeline = run.audit_summary.get("pipeline") or {}
        self.assertIn("advance", pipeline)
        self.assertIn("apply", pipeline)
