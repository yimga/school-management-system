from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires


ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_CENTER = ROOT / "templates" / "schools" / "super_migration_cloud.html"


class MigrationAppleClassUXTests(SimpleTestCase):
    def test_migration_center_has_data_quality_visual(self):
        text = (ROOT / "templates" / "schools" / "super_migration_cloud.html").read_text(encoding="utf-8")
        # Every one of these four is a {% trans %} msgid, so it is template code
        # and only the source read can see it.
        for token in (
            "Data Quality Meter",
            "Field mapping",
            "duplicate",
            "rollback posture",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
        # The surface marker is markup and the meter is an {% include %}. Both are
        # things the engine can answer and a {% comment %} cannot fake -- and a
        # commented-out meter is precisely "no data-quality visual".
        assert_markup(self, _MIGRATION_CENTER, "data-apple-class-migration-ux")
        assert_wires(self, _MIGRATION_CENTER, "apple_class_data_quality_meter.html")
