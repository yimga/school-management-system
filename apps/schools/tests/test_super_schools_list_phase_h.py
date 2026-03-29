"""Phase H skip-link regression for super schools list (batch 34 #421)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase


class SuperSchoolsListPhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        path = Path(settings.BASE_DIR) / "templates" / "schools" / "super_schools_list.html"
        text = path.read_text(encoding="utf-8")
        self.assertIn('href="#super-schools-list-main"', text)
        self.assertIn('id="super-schools-list-main"', text)
