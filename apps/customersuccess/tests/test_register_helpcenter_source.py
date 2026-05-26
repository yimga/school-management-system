"""Tests for apps.customersuccess.services.register_helpcenter_source."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.customersuccess import services
from apps.schools.models import School


class RegisterHelpcenterSourceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Helpcenter School",
            slug="helpcenter-school",
            subdomain="helpcenter-school",
            is_active=True,
        )

    def _ledger(self):
        self.school.refresh_from_db()
        cs = (self.school.settings or {}).get("customersuccess") or {}
        return cs.get("helpcenter_sources") or []

    def test_url_value_lands_in_ledger(self):
        ok = services.register_helpcenter_source(
            school=self.school,
            payload={"value": "https://help.example.com/article/1"},
        )
        self.assertTrue(ok)
        ledger = self._ledger()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["value"], "https://help.example.com/article/1")
        self.assertIn("registered_at_iso", ledger[0])

    def test_file_upload_metadata_recorded(self):
        f = SimpleUploadedFile("policy.pdf", b"x" * 256, content_type="application/pdf")
        ok = services.register_helpcenter_source(
            school=self.school,
            payload={"value": f},
        )
        self.assertTrue(ok)
        ledger = self._ledger()
        self.assertEqual(ledger[0]["file_name"], "policy.pdf")
        self.assertEqual(ledger[0]["file_size"], 256)

    def test_file_shape_dict_from_sanitizer(self):
        """When _sanitize_for_storage already converted a file to {file_name, file_size}."""
        ok = services.register_helpcenter_source(
            school=self.school,
            payload={"value": {"file_name": "faq.pdf", "file_size": 1024}},
        )
        self.assertTrue(ok)
        ledger = self._ledger()
        self.assertEqual(ledger[0]["file_name"], "faq.pdf")
        self.assertEqual(ledger[0]["file_size"], 1024)

    def test_duplicate_value_idempotent(self):
        services.register_helpcenter_source(
            school=self.school,
            payload={"value": "https://help.example.com/a"},
        )
        self.assertFalse(
            services.register_helpcenter_source(
                school=self.school,
                payload={"value": "https://help.example.com/a"},
            )
        )

    def test_no_op_inputs(self):
        self.assertFalse(services.register_helpcenter_source(school=None, payload={"value": "x"}))
        self.assertFalse(services.register_helpcenter_source(school=self.school, payload={}))
        self.assertFalse(services.register_helpcenter_source(school=self.school, payload={"value": ""}))
        self.assertFalse(services.register_helpcenter_source(school=self.school, payload={"value": None}))
