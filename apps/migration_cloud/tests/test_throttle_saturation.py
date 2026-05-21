"""v3.40.0 Agent 15 — throttle bucket saturation alert hook tests.

Coverage (~6 tests):
  * Bucket at 96% → alert fired
  * Bucket at 90% → no alert (below 0.95 default threshold)
  * Same bucket within 1h cooldown → no second alert
  * Disabled flag → no alert ever
  * Defensive import: if ``alert`` not importable → silent skip
  * Ratio threshold tunable via setting
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.migration_cloud.api import rate_limiting


class ThrottleSaturationAlertTests(SimpleTestCase):

    def setUp(self):
        # Each test starts from a clean cooldown ledger.
        rate_limiting._reset_saturation_cooldown_for_tests()

    def test_saturation_above_default_threshold_fires_alert(self):
        with mock.patch(
            "apps.migration_cloud.alerts.alert"
        ) as mock_alert:
            rate_limiting._check_saturation_alert(
                bucket_name="webhook_tenant:tok-42",
                current=96,
                limit=100,
            )
            self.assertTrue(mock_alert.called)
            kwargs = mock_alert.call_args.kwargs
            self.assertEqual(kwargs.get("severity"), "warning")
            # Title must contain a sha256 prefix, NOT the raw bucket key.
            title = kwargs.get("title", "")
            self.assertNotIn("webhook_tenant:tok-42", title)
            self.assertIn("Migration Cloud rate-limit saturation", title)

    def test_below_threshold_no_alert(self):
        with mock.patch(
            "apps.migration_cloud.alerts.alert"
        ) as mock_alert:
            rate_limiting._check_saturation_alert(
                bucket_name="bundles_read:usr-1",
                current=90,
                limit=100,
            )
            self.assertFalse(mock_alert.called)

    def test_cooldown_blocks_second_alert_within_window(self):
        with mock.patch(
            "apps.migration_cloud.alerts.alert"
        ) as mock_alert:
            rate_limiting._check_saturation_alert(
                bucket_name="cooldown-test:tok-7",
                current=96, limit=100,
            )
            rate_limiting._check_saturation_alert(
                bucket_name="cooldown-test:tok-7",
                current=98, limit=100,
            )
            self.assertEqual(mock_alert.call_count, 1)

    @override_settings(
        MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_DISABLED=True,
    )
    def test_disabled_flag_suppresses_alert(self):
        with mock.patch(
            "apps.migration_cloud.alerts.alert"
        ) as mock_alert:
            rate_limiting._check_saturation_alert(
                bucket_name="disabled-test:tok-9",
                current=99, limit=100,
            )
            self.assertFalse(mock_alert.called)

    def test_defensive_import_when_alert_unavailable(self):
        """If the alerts module cannot be imported, no exception bubbles up.

        We simulate the missing-module case by replacing the cached
        ``apps.migration_cloud.alerts`` module entry with one whose
        ``alert`` attribute raises on access — emulating a partially-
        loaded module / import-time failure. Must NOT crash the
        throttle path.
        """
        import sys
        import types

        # Construct a stand-in module whose ``alert`` raises when called.
        bogus = types.ModuleType("apps.migration_cloud.alerts")
        def _boom(**kwargs):
            raise RuntimeError("simulated alerts unavailable")
        bogus.alert = _boom  # type: ignore[attr-defined]
        original = sys.modules.get("apps.migration_cloud.alerts")
        sys.modules["apps.migration_cloud.alerts"] = bogus
        try:
            # Must NOT raise — the rate-limiting hook catches the
            # downstream RuntimeError as a defense-in-depth measure.
            rate_limiting._check_saturation_alert(
                bucket_name="defensive-import-test:tok-1",
                current=99, limit=100,
            )
        finally:
            if original is not None:
                sys.modules["apps.migration_cloud.alerts"] = original
            else:
                sys.modules.pop("apps.migration_cloud.alerts", None)

    @override_settings(MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_RATIO=0.5)
    def test_ratio_threshold_tunable_via_setting(self):
        with mock.patch(
            "apps.migration_cloud.alerts.alert"
        ) as mock_alert:
            # 60% > 50% threshold → alert.
            rate_limiting._check_saturation_alert(
                bucket_name="tunable-threshold:tok-3",
                current=60, limit=100,
            )
            self.assertTrue(mock_alert.called)
