"""Phase H skip-link regression for super dashboard (batch 33 #406)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase


class SuperDashboardPhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        dashboard = Path(settings.BASE_DIR) / "templates" / "schools" / "super_dashboard.html"
        world_map = (
            Path(settings.BASE_DIR) / "templates" / "partials" / "cockpit" / "_live_world_map.html"
        )
        dashboard_text = dashboard.read_text(encoding="utf-8")
        world_map_text = world_map.read_text(encoding="utf-8")
        self.assertIn('href="#rmc-globe-master-lab"', dashboard_text)
        self.assertIn('id="rmc-globe-master-lab"', world_map_text)
