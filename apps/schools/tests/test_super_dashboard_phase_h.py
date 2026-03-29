"""Phase H skip-link regression for super dashboard (batch 33 #406)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase


class SuperDashboardPhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        path = Path(settings.BASE_DIR) / "templates" / "schools" / "super_dashboard.html"
        text = path.read_text(encoding="utf-8")
        self.assertIn('href="#super-dashboard-main"', text)
        self.assertIn('id="super-dashboard-main"', text)
