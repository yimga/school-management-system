from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class SuperCommandCenterExperienceTests(SimpleTestCase):
    def test_super_dashboard_has_world_class_above_fold_contract(self):
        text = (ROOT / "templates" / "schools" / "super_dashboard.html").read_text(encoding="utf-8")
        self.assertIn("world_class_page_hero.html", text)
        self.assertIn("Platform Command Center", text)
        self.assertIn("world_class_summary_strip.html", text)
        self.assertIn("data-world-class-super-sections", text)
        self.assertIn("platform-pulse tenant-risk implementation-pipeline", text)
        self.assertIn("External blockers", text)
        self.assertIn("Proof Ledger", text)
