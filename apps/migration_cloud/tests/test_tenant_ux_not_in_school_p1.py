"""P1-UX — tenant upload/review must state that upload ≠ school import."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

BUNDLE_REVIEW = Path("templates/migration_cloud/connector/bundle_review.html")
UPLOAD = Path("templates/migration_cloud/connector/upload.html")


class TenantMigrationUxCopyTests(SimpleTestCase):
    def test_review_has_not_in_school_yet_banner(self):
        text = Path("templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        # The banner copy is {% trans %} output, and the page does not render
        # standalone (it extends _wizard_base, which needs SITE), so the wording
        # itself has to stay a source read.
        self.assertIn("Not in your school yet", text)
        # The section that carries the banner, the banner's own warning class and
        # the live-import hook are all emitted markup -- ask the engine for them.
        assert_markup(
            self,
            BUNDLE_REVIEW,
            'data-mc-live-import="1"',
            'id="mc-import-heading"',
            "rmc-alert-banner--warning",
        )

    def test_upload_states_upload_does_not_import(self):
        text = Path("templates/migration_cloud/connector/upload.html").read_text(
            encoding="utf-8"
        )
        # {% trans %} output again, and again no standalone render: the wording
        # stays a source read.
        self.assertIn("Upload does not import", text)
        # The upload surface that carries that copy must still exist, though: it
        # wires the connector wizard base and emits its own heading, its offline
        # form marker and its file input.
        assert_wires(self, UPLOAD, "migration_cloud/connector/_wizard_base.html")
        assert_markup(
            self,
            UPLOAD,
            'id="mc-upload-heading"',
            'data-rmc-offline-form="migration_cloud_upload"',
            'id="mc-artifacts"',
        )

    def test_upload_success_message_mentions_import_gate(self):
        src = Path("apps/migration_cloud/views_tenant_upload.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Nothing is in your school until you click", src)
