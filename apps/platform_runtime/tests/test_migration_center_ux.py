from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class MigrationCenterUXTests(SimpleTestCase):
    def test_migration_cloud_has_visual_flow_quality_quarantine_and_rollback(self):
        text = (ROOT / "templates" / "schools" / "super_migration_cloud.html").read_text(encoding="utf-8")
        # super_migration_cloud adopted the shared operational-center frame: the
        # "Migration Center" hero is now the frame's masthead
        # (os_center_key="migration_center" + center_title context), replacing the
        # standalone world_class_page_hero; the guided stepper is unchanged.
        self.assertIn("rmc_operational_center_frame.html", text)
        self.assertIn('os_center_key="migration_center"', text)
        self.assertIn("world_class_guided_stepper.html", text)
        self.assertIn("Data quality", text)
        self.assertIn("Quarantine", text)
        self.assertIn("Rollback", text)
        self.assertIn("summary.quarantine_pending", text)
