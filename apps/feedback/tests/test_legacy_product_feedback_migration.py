from __future__ import annotations

from django.test import SimpleTestCase

from apps.feedback.legacy_product_feedback_migration import (
    LEGACY_MARKER_PREFIX,
)


class LegacyProductFeedbackMigrationTests(SimpleTestCase):
    def test_marker_prefix_stable(self):
        self.assertTrue(LEGACY_MARKER_PREFIX.startswith("[legacy-product-feedback:"))

    def test_dry_run_summary_shape(self):
        from apps.feedback.legacy_product_feedback_migration import MigrationSummary

        summary = MigrationSummary(dry_run=True, scanned=2, created=2)
        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.scanned, 2)
