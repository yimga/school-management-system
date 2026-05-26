"""Tests for v3.94.0 HelpcenterSource first-class promotion.

Covers:
* Wizard writer creates a HelpcenterSource row alongside the legacy ledger entry.
* Both URL and FILE kinds work.
* Per-school unique constraints prevent duplicate URL / filename entries.
* Backfill management command migrates legacy ledger entries idempotently.
"""

from __future__ import annotations

from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from apps.customersuccess import services
from apps.customersuccess.models import HelpcenterSource
from apps.schools.models import School


class HelpcenterSourceFirstClassPromotionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="HC Promotion School",
            slug="hc-promotion-school",
            subdomain="hc-promotion-school",
            is_active=True,
        )

    def test_url_registration_creates_first_class_row(self):
        services.register_helpcenter_source(
            school=self.school,
            payload={"value": "https://help.example.com/policy"},
        )
        # tenant-isolation-allow: test-scoped-explicit-school-fk
        rows = list(HelpcenterSource.objects.filter(school=self.school))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, HelpcenterSource.Kind.URL)
        self.assertEqual(rows[0].url, "https://help.example.com/policy")

    def test_file_registration_creates_first_class_row(self):
        f = SimpleUploadedFile("policy.pdf", b"x" * 512, content_type="application/pdf")
        services.register_helpcenter_source(school=self.school, payload={"value": f})
        # tenant-isolation-allow: test-scoped-explicit-school-fk
        rows = list(HelpcenterSource.objects.filter(school=self.school))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, HelpcenterSource.Kind.FILE)
        self.assertEqual(rows[0].file_name, "policy.pdf")
        self.assertEqual(rows[0].file_size, 512)

    def test_duplicate_url_dedup_via_unique_constraint(self):
        services.register_helpcenter_source(
            school=self.school, payload={"value": "https://help.example.com/x"},
        )
        # Second call returns False from the ledger dedup BEFORE first-class write,
        # so we should still have only 1 row.
        services.register_helpcenter_source(
            school=self.school, payload={"value": "https://help.example.com/x"},
        )
        # tenant-isolation-allow: test-scoped-explicit-school-fk
        self.assertEqual(HelpcenterSource.objects.filter(school=self.school).count(), 1)


class BackfillCommandTests(TestCase):
    """Verifies promote_helpcenter_ledger_to_first_class is idempotent + correct."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Backfill School",
            slug="backfill-school",
            subdomain="backfill-school",
            is_active=True,
        )
        # Seed a legacy ledger directly (simulating v3.93.3-shipped data).
        cls.school.settings = {
            "customersuccess": {
                "helpcenter_sources": [
                    {
                        "value": "https://help.example.com/article-1",
                        "registered_at_iso": "2026-05-25T10:00:00+00:00",
                    },
                    {
                        "file_name": "manual.pdf",
                        "file_size": 1024,
                        "registered_at_iso": "2026-05-25T11:00:00+00:00",
                    },
                ],
            },
        }
        cls.school.save(update_fields=["settings"])

    def test_dry_run_does_not_write(self):
        out = StringIO()
        call_command("promote_helpcenter_ledger_to_first_class", stdout=out)
        # tenant-isolation-allow: test-scoped-explicit-school-fk
        self.assertEqual(HelpcenterSource.objects.filter(school=self.school).count(), 0)
        self.assertIn("Dry-run only", out.getvalue())

    def test_apply_writes_first_class_rows(self):
        out = StringIO()
        call_command("promote_helpcenter_ledger_to_first_class", "--apply", stdout=out)
        # tenant-isolation-allow: test-scoped-explicit-school-fk
        rows = list(HelpcenterSource.objects.filter(school=self.school).order_by("kind"))
        self.assertEqual(len(rows), 2)
        kinds = {r.kind for r in rows}
        self.assertEqual(kinds, {HelpcenterSource.Kind.URL, HelpcenterSource.Kind.FILE})

    def test_apply_idempotent_on_re_run(self):
        call_command("promote_helpcenter_ledger_to_first_class", "--apply", stdout=StringIO())
        # Re-run: should not duplicate.
        out = StringIO()
        call_command("promote_helpcenter_ledger_to_first_class", "--apply", stdout=out)
        # tenant-isolation-allow: test-scoped-explicit-school-fk
        self.assertEqual(HelpcenterSource.objects.filter(school=self.school).count(), 2)
