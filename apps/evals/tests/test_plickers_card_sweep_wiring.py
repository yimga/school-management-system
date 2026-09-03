from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.models_support import default_backend_feature_flags
from apps.siteconfig.tests._template_nodes import assert_markup


ROOT = Path(__file__).resolve().parents[3]
_MARKS_ENTRY = ROOT / "templates/teacher/marks_entry.html"


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
        # The bundle name is a {% static %} argument, never emitted text.
        self.assertIn("rmc-plickers-card-sweep.js", template)
        self.assertIn("BarcodeDetector", source)
        self.assertNotIn(".submit(", source)
        self.assertNotIn("fetch(", source)
        # The start hook is markup and it is what the camera runtime binds to: a
        # {% comment %} keeps the string in the bytes and leaves the runtime with
        # nothing to attach to. Ask the engine what marks_entry EMITS.
        assert_markup(self, _MARKS_ENTRY, "rmc-card-sweep-start")
