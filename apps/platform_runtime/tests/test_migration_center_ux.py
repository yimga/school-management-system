from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class MigrationCenterUXTests(SimpleTestCase):
    def test_migration_cloud_has_visual_flow_quality_quarantine_and_rollback(self):
        text = (ROOT / "templates" / "schools" / "super_migration_cloud.html").read_text(encoding="utf-8")
        self.assertIn("Migration Center", text)
        self.assertIn("world_class_page_hero.html", text)
        self.assertIn("world_class_guided_stepper.html", text)
        self.assertIn("Data quality", text)
        self.assertIn("Quarantine", text)
        self.assertIn("Rollback", text)
        self.assertIn("summary.quarantine_pending", text)
