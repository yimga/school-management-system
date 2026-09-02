"""P2 honesty — DFV-only domains + legacy wizard deprecation."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

BUNDLE_REVIEW = Path("templates/migration_cloud/connector/bundle_review.html")
MIGRATION_WIZARD = Path("templates/accounts/migration_wizard.html")


class DfvHonestyBadgeTests(SimpleTestCase):
    def test_review_template_has_custom_records_badge(self):
        text = Path("templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        # Both needles are template CODE: the badge copy is inside {% trans %}
        # and row.dfv_only is an {% if %} condition, so neither a parse nor a
        # render can see them and both stay reads. What a parse settles is that
        # the review surface is still a wizard page that emits the badge
        # element the copy sits in.
        assert_wires(self, BUNDLE_REVIEW, "migration_cloud/connector/_wizard_base.html")
        assert_markup(self, BUNDLE_REVIEW, '<span class="rmc-badge">')
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
        # "Points to Migration Cloud" is the HREF, and that one is a hardcoded
        # literal rather than a {% url %} tag, so the engine can confirm the
        # banner really emits it -- along with the banner element itself. The
        # title copy is inside {% trans %} and stays a read.
        assert_markup(
            self,
            MIGRATION_WIZARD,
            "/school/setup/migration-cloud/upload/",
            "rmc-alert-banner--warning",
            "rmc-alert-banner__title",
        )
        self.assertIn("Prefer Migration Cloud", text)
        self.assertIn("/school/setup/migration-cloud/upload/", text)
