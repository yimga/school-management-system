"""Connector registry and profile tests."""

from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase

from apps.migration_cloud.connectors import get_connector, list_connectors
from apps.migration_cloud.models_connectors import MigrationConnectorProfile


class ConnectorRegistryTests(TestCase):
    def test_adapters_registered(self):
        connectors = list_connectors()
        self.assertIn("generic_csv_export", connectors)
        self.assertIn("powerschool", connectors)

    def test_generic_export_certification(self):
        adapter = get_connector("generic_csv_export")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.certification, "production_ready")

    def test_powerschool_pilot_ready(self):
        adapter = get_connector("powerschool")
        self.assertEqual(adapter.certification, "pilot_ready")

    def test_seed_command(self):
        call_command("seed_migration_connector_profiles")
        self.assertTrue(
            MigrationConnectorProfile.objects.filter(key="generic_csv_export").exists()
        )
