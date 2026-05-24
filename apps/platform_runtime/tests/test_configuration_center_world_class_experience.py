from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class ConfigurationCenterWorldClassExperienceTests(SimpleTestCase):
    def test_configuration_center_groups_modules_with_readiness_and_actions(self):
        text = (ROOT / "templates" / "platform_runtime" / "configuration_center.html").read_text(encoding="utf-8")
        frame = (ROOT / "templates" / "components" / "rmc_operational_center_frame.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operational_center_frame.html", text)
        self.assertIn("data-rmc-operational-center-frame", frame)
        self.assertIn("data-rmc-ops-nav-grid", frame)
        self.assertIn("cp-steering", frame)
        self.assertIn("cp-steering__path", frame)
        self.assertIn("cp-btn--primary", frame)
        self.assertIn("Platform Configuration Center", text)
        self.assertIn("data-world-class-module-groups", text)
        for group in ("operating-models", "runtime-governance", "data-migration", "ecosystem", "trust-money", "experience"):
            self.assertIn(group, text)
        self.assertIn("data-world-class-readiness-score", text)
        self.assertIn("data-world-class-mobile-layout", text)

    def test_experience_standard_exists(self):
        standard = ROOT / "docs" / "design" / "RUNMYCAMPUS_WORLD_CLASS_EXPERIENCE_STANDARD.md"
        text = standard.read_text(encoding="utf-8")
        for phrase in ("Core Feel", "Accessibility", "Dashboard Rules", "Mobile Rules", "Proof Standard"):
            self.assertIn(phrase, text)
