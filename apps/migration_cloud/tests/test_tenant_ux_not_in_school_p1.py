"""P1-UX — tenant upload/review must state that upload ≠ school import."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


class TenantMigrationUxCopyTests(SimpleTestCase):
    def test_review_has_not_in_school_yet_banner(self):
        text = Path("templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Not in your school yet", text)
        self.assertIn('data-mc-live-import="1"', text)

    def test_upload_states_upload_does_not_import(self):
        text = Path("templates/migration_cloud/connector/upload.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Upload does not import", text)

    def test_upload_success_message_mentions_import_gate(self):
        src = Path("apps/migration_cloud/views_tenant_upload.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Nothing is in your school until you click", src)
