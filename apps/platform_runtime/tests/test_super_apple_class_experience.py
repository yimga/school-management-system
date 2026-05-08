from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class SuperAppleClassExperienceTests(SimpleTestCase):
    def test_super_command_center_has_apple_class_above_fold(self):
        text = (ROOT / "templates" / "schools" / "super_dashboard.html").read_text(encoding="utf-8")
        for token in (
            "data-apple-class-super-command-center",
            "data-apple-class-command-strip",
            "Platform Health",
            "Schools Needing Attention",
            "External Blockers",
            "apple_class_quick_profile_drawer.html",
            "Open detailed operating board",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
