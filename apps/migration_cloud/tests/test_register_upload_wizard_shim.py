"""Tests for apps.migration_cloud.companion_receiver.register_upload (wizard shim).

Distinct from the full CompanionUploadView handshake — this records setup-time
wizard answers in a tenant-scoped ledger on ``school.settings["migration_cloud"]``.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.migration_cloud import companion_receiver
from apps.schools.models import School


class RegisterUploadWizardShimTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Migration School",
            slug="migration-school",
            subdomain="migration-school",
            is_active=True,
        )

    def _ledger(self):
        self.school.refresh_from_db()
        mc = (self.school.settings or {}).get("migration_cloud") or {}
        return mc.get("wizard_uploads") or []

    def test_file_upload_recorded(self):
        f = SimpleUploadedFile("legacy.csv", b"x" * 512, content_type="text/csv")
        ok = companion_receiver.register_upload(
            school=self.school,
            payload={"value": f},
            actor_user_id=42,
        )
        self.assertTrue(ok)
        ledger = self._ledger()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["file_name"], "legacy.csv")
        self.assertEqual(ledger[0]["file_size"], 512)
        self.assertEqual(ledger[0]["actor_user_id"], 42)
        self.assertIn("registered_at_iso", ledger[0])

    def test_dict_shape_file_payload(self):
        ok = companion_receiver.register_upload(
            school=self.school,
            payload={"value": {"file_name": "students.csv", "file_size": 1024}},
        )
        self.assertTrue(ok)
        ledger = self._ledger()
        self.assertEqual(ledger[0]["file_name"], "students.csv")

    def test_duplicate_filename_idempotent(self):
        companion_receiver.register_upload(
            school=self.school,
            payload={"value": {"file_name": "x.csv", "file_size": 1}},
        )
        self.assertFalse(
            companion_receiver.register_upload(
                school=self.school,
                payload={"value": {"file_name": "x.csv", "file_size": 2}},
            )
        )

    def test_no_op_inputs(self):
        self.assertFalse(companion_receiver.register_upload(school=None, payload={"value": "x"}))
        self.assertFalse(companion_receiver.register_upload(school=self.school, payload={}))
        self.assertFalse(companion_receiver.register_upload(school=self.school, payload={"value": ""}))
