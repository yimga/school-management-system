from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class MigrationAppleClassUXTests(SimpleTestCase):
    def test_migration_center_has_data_quality_visual(self):
        text = (ROOT / "templates" / "schools" / "super_migration_cloud.html").read_text(encoding="utf-8")
        for token in (
            "data-apple-class-migration-ux",
            "Data Quality Meter",
            "Field mapping",
            "duplicate",
            "rollback posture",
            "apple_class_data_quality_meter.html",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
