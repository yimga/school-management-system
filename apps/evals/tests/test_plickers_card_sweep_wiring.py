from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.models_support import default_backend_feature_flags


ROOT = Path(__file__).resolve().parents[3]


class PlickersCardSweepWiringTests(SimpleTestCase):
    def test_feature_flag_defaults_on(self):
        self.assertTrue(default_backend_feature_flags()["plickers_card_sweep_enabled"])

    def test_marks_entry_loads_proposal_only_camera_runtime(self):
        template = (ROOT / "templates/teacher/marks_entry.html").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "static/js/rmc-plickers-card-sweep.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-card-sweep-start", template)
        self.assertIn("rmc-plickers-card-sweep.js", template)
        self.assertIn("BarcodeDetector", source)
        self.assertNotIn(".submit(", source)
        self.assertNotIn("fetch(", source)
