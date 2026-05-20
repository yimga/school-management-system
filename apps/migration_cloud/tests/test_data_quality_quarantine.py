"""Data quality and quarantine tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import (
    MigrationConnectorProfile,
    MigrationDiscoveryRun,
    QuarantineItemStatus,
)
from apps.migration_cloud.services.connector_credentials import create_source_connection
from apps.migration_cloud.services.connector_discovery import stage_entity_preview

User = get_user_model()


class DataQualityQuarantineTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="DQ School", slug="dq-test", subdomain="dq-test"
        )
        self.user = User.objects.create_user(username="dq_user", password="unused")
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
        self.run = MigrationDiscoveryRun.objects.create(
            school=self.school,
            source_connection=self.conn,
            started_by=self.user,
        )

    def test_invalid_rows_quarantined(self):
        batch, items = stage_entity_preview(
            connection=self.conn,
            discovery_run=self.run,
            entity_type="students",
            rows=[{"email": "only@example.com"}],
        )
        self.assertGreater(batch.invalid_count, 0)
        self.assertTrue(items)
        self.assertEqual(items[0].status, QuarantineItemStatus.OPEN)

    def test_score_calculated(self):
        batch, _ = stage_entity_preview(
            connection=self.conn,
            discovery_run=self.run,
            entity_type="students",
            rows=[
                {
                    "admission_number": "A1",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                }
            ],
        )
        self.assertIsNotNone(batch.data_quality_score)
