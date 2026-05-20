"""Vendor connector certification tests (synthetic fixture evidence)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.migration_cloud.connectors import get_connector

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class VendorConnectorTests(SimpleTestCase):
    def test_powerschool_pilot_ready_with_fixture(self):
        adapter = get_connector("powerschool")
        self.assertEqual(adapter.certification, "pilot_ready")
        path = _FIXTURES / "synthetic_powerschool.csv"
        ok, blockers = adapter.verify_connection(
            source_url="https://powerschool.example.edu",
            credentials={"export_path": str(path)},
        )
        self.assertTrue(ok, blockers)
        preview = adapter.extract_entity(
            "students",
            source_url="https://powerschool.example.edu",
            credentials={"export_path": str(path)},
        )
        self.assertGreater(preview.estimated_count, 0)
        self.assertTrue(preview.sample_records)

    def test_blackbaud_fixture(self):
        adapter = get_connector("blackbaud")
        path = _FIXTURES / "synthetic_blackbaud.csv"
        ok, _ = adapter.verify_connection(
            source_url="https://bb.example.edu",
            credentials={"export_path": str(path)},
        )
        self.assertTrue(ok)

    def test_google_classroom_oauth_token_gate(self):
        adapter = get_connector("google_classroom")
        ok, blockers = adapter.verify_connection(
            source_url="https://classroom.google.com",
            credentials={},
        )
        self.assertFalse(ok)
        self.assertIn("oauth_token_required", blockers)
