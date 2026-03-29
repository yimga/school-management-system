"""Phase H skip-link regression for super analytics overview (batch 35 #436)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase


class SuperAnalyticsOverviewPhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "schools"
            / "super_analytics_overview.html"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn('href="#analytics-overview-main"', text)
        self.assertIn('id="analytics-overview-main"', text)
