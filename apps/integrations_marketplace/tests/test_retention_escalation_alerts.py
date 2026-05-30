"""v4.00.92 — Unit tests for ``retention_escalation_alerts`` (W19 module).

In-process ring buffer. No DB writes. SimpleTestCase.

Coverage:
  * check_large_batch_threshold — warning@1000 + critical@10x
  * check_override_below_floor — warning<3y + critical<floor/2
  * retention_alerts_summary — counts by severity
  * reset_retention_alerts — clear all
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.integrations_marketplace import retention_escalation_alerts as _ra


class RetentionEscalationAlertsTests(SimpleTestCase):

    def setUp(self):
        _ra.reset_retention_alerts()

    def tearDown(self):
        _ra.reset_retention_alerts()

    def test_check_large_batch_warning_at_threshold(self):
        """count == threshold -> warning alert emitted."""
        alert = _ra.check_large_batch_threshold(
            tenant_schema="acme",
            target_table="lms_diag_action_audit",
            count=1000,
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert["severity"], "warning")
        self.assertEqual(alert["alert_type"], "large_batch_pending_purge")
        self.assertEqual(alert["count"], 1000)

    def test_check_large_batch_critical_at_10x(self):
        """count >= threshold * 10 -> critical alert emitted."""
        alert = _ra.check_large_batch_threshold(
            tenant_schema="acme",
            target_table="lms_diag_action_audit",
            count=10000,
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert["severity"], "critical")
        # Below threshold -> None, no alert.
        below = _ra.check_large_batch_threshold(
            tenant_schema="acme",
            target_table="lms_diag_action_audit",
            count=500,
        )
        self.assertIsNone(below)

    def test_check_override_below_floor_warning(self):
        """retention_years < floor (but >= floor/2) -> warning."""
        # floor=3 default; floor/2 = 1, so 2 yields warning.
        alert = _ra.check_override_below_floor(
            tenant_schema="acme",
            target_table="lms_diag_action_audit",
            retention_years=2,
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert["severity"], "warning")
        self.assertEqual(alert["alert_type"], "override_below_regulatory_floor")
        # retention_years == floor -> no alert.
        none_alert = _ra.check_override_below_floor(
            tenant_schema="acme", target_table="lms_diag_action_audit",
            retention_years=3,
        )
        self.assertIsNone(none_alert)

    def test_check_override_below_floor_critical(self):
        """retention_years < floor/2 -> critical."""
        # floor=10, floor/2 = 5, so 4 yields critical.
        alert = _ra.check_override_below_floor(
            tenant_schema="acme",
            target_table="lms_diag_action_audit",
            retention_years=4,
            floor=10,
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert["severity"], "critical")
        # retention_years == 0 means "retain forever" -> no alert.
        none_alert = _ra.check_override_below_floor(
            tenant_schema="acme", target_table="lms_diag_action_audit",
            retention_years=0, floor=10,
        )
        self.assertIsNone(none_alert)

    def test_retention_alerts_summary_counts(self):
        """Summary counts each severity bucket."""
        _ra.check_large_batch_threshold(
            tenant_schema="acme", target_table="t", count=1000,
        )  # warning
        _ra.check_large_batch_threshold(
            tenant_schema="acme", target_table="t", count=20000,
        )  # critical
        _ra.check_override_below_floor(
            tenant_schema="acme", target_table="t", retention_years=2,
        )  # warning
        summary = _ra.retention_alerts_summary()
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["by_severity"]["warning"], 2)
        self.assertEqual(summary["by_severity"]["critical"], 1)
        self.assertEqual(summary["by_severity"]["info"], 0)

    def test_reset_retention_alerts_clears_ring(self):
        """Reset wipes the ring; subsequent summary is all-zero."""
        _ra.check_large_batch_threshold(
            tenant_schema="acme", target_table="t", count=5000,
        )
        self.assertGreater(_ra.retention_alerts_summary()["total"], 0)
        _ra.reset_retention_alerts()
        summary = _ra.retention_alerts_summary()
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["by_severity"]["warning"], 0)
        self.assertEqual(summary["by_severity"]["critical"], 0)
