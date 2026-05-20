"""Field mapping tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.models_connectors import FieldMappingStatus, MigrationConnectorProfile
from apps.migration_cloud.services.connector_credentials import create_source_connection
from apps.migration_cloud.services.connector_mapping import (
    confirm_mappings,
    required_fields_blocked,
    suggest_field_mappings,
)

User = get_user_model()


class FieldMappingTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Map School", slug="map-test", subdomain="map-test"
        )
        self.user = User.objects.create_user(username="map_user", password="unused")
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

    def test_suggest_and_confirm_mapping(self):
        mappings = suggest_field_mappings(
            connection=self.conn,
            entity_type="students",
            source_fields=["admission_number", "first_name", "last_name", "unknown_col"],
            actor=self.user,
        )
        self.assertGreaterEqual(len(mappings), 3)
        confirm_mappings(connection=self.conn, entity_type="students", actor=self.user)
        confirmed = self.conn.field_mappings.filter(status=FieldMappingStatus.CONFIRMED).count()
        self.assertGreaterEqual(confirmed, 3)

    def test_required_missing_blocks_import(self):
        suggest_field_mappings(
            connection=self.conn,
            entity_type="students",
            source_fields=["email"],
            actor=self.user,
        )
        missing = required_fields_blocked(self.conn, "students")
        self.assertIn("admission_number", missing)
