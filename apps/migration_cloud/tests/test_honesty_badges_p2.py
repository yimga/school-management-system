"""P2 honesty — DFV-only domains + legacy wizard deprecation."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


class DfvHonestyBadgeTests(SimpleTestCase):
    def test_review_template_has_custom_records_badge(self):
        text = Path("templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("stored as custom records", text)
        self.assertIn("row.dfv_only", text)

    def test_view_marks_payroll_compliance_dfv_only(self):
        src = Path("apps/migration_cloud/views_tenant_upload.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('detected in ("payroll", "compliance")', src)


class LegacyWizardDeprecationTests(SimpleTestCase):
    def test_banner_points_to_migration_cloud(self):
        text = Path("templates/accounts/migration_wizard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Prefer Migration Cloud", text)
        self.assertIn("/school/setup/migration-cloud/upload/", text)
