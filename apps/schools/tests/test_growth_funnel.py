"""Growth funnel snapshot does not fabricate conversion rates at zero volume."""

import os
from unittest.mock import patch

from django.test import TestCase

from apps.schools.growth_analytics import FUNNEL_STAGE_ORDER, build_growth_funnel_snapshot


class GrowthAnalyticsTests(TestCase):
    databases = {"default"}

    def test_empty_snapshot_no_conversion_claim(self):
        snap = build_growth_funnel_snapshot(days=30)
        self.assertEqual(snap["verdict"], "NOT_READY")
        self.assertTrue(snap["insufficient_volume_for_claims"])
        self.assertIsNone(snap["conversion_visit_to_subscription_pct"])
        self.assertEqual(len(FUNNEL_STAGE_ORDER), 17)


class EnsureDemoScheduledTaskTests(TestCase):
    """Celery wrapper for ensure_demo_environment is opt-in via ENSURE_DEMO_CRON_SLUG."""

    def test_scheduled_demo_refresh_skips_when_slug_unset(self):
        from apps.schools.tasks import ensure_demo_environment_scheduled

        with patch.dict(os.environ, {"ENSURE_DEMO_CRON_SLUG": ""}):
            out = ensure_demo_environment_scheduled()
        self.assertEqual(out.get("skipped"), True)

    @patch("django.core.management.call_command")
    def test_scheduled_demo_refresh_calls_command_when_slug_set(self, mock_cc):
        from apps.schools.tasks import ensure_demo_environment_scheduled

        with patch.dict(os.environ, {"ENSURE_DEMO_CRON_SLUG": "demo-school"}):
            out = ensure_demo_environment_scheduled()
        self.assertEqual(out.get("ok"), True)
        mock_cc.assert_called_once()
        call_kw = mock_cc.call_args
        self.assertEqual(call_kw[0][0], "ensure_demo_environment")
        self.assertEqual(call_kw[1]["school_slug"], "demo-school")
