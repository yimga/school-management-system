from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires


ROOT = Path(__file__).resolve().parents[3]
_CONFIGURATION_CENTER = (
    ROOT / "templates" / "platform_runtime" / "configuration_center.html"
)


class ConfigurationCenterWorldClassExperienceTests(SimpleTestCase):
    def test_configuration_center_groups_modules_with_readiness_and_actions(self):
        text = (ROOT / "templates" / "platform_runtime" / "configuration_center.html").read_text(encoding="utf-8")
        frame = (ROOT / "templates" / "components" / "rmc_operational_center_frame.html").read_text(encoding="utf-8")
        # The frame's steering/nav markup moved into the _inner partial, and the
        # primary CTA into the shared masthead partial, that the frame composes;
        # fold both in so the marker checks see the current, distributed markup.
        frame += "\n" + (ROOT / "templates" / "components" / "rmc_operational_center_frame_inner.html").read_text(encoding="utf-8")
        frame += "\n" + (ROOT / "templates" / "components" / "rmc_page_masthead.html").read_text(encoding="utf-8")
        # The frame half is a concatenation of THREE files, which no single parse
        # can model, so those four stay source reads. The page title is a
        # {% trans %} msgid, also invisible to a parse.
        self.assertIn("data-rmc-operational-center-frame", frame)
        self.assertIn("data-rmc-ops-nav-grid", frame)
        self.assertIn("cp-steering", frame)
        self.assertIn("cp-steering__path", frame)
        self.assertIn("cp-btn--primary", frame)
        self.assertIn("Platform Configuration Center", text)
        # Everything about the configuration center itself is wiring or markup,
        # and a {% comment %} keeps all of it in the bytes while rendering none:
        assert_wires(self, _CONFIGURATION_CENTER, "rmc_operational_center_frame.html")
        assert_markup(
            self,
            _CONFIGURATION_CENTER,
            "data-world-class-module-groups",
            "operating-models",
            "runtime-governance",
            "data-migration",
            "ecosystem",
            "trust-money",
            "experience",
            "data-world-class-readiness-score",
            "data-world-class-mobile-layout",
        )

    def test_experience_standard_exists(self):
        standard = ROOT / "docs" / "design" / "RUNMYCAMPUS_WORLD_CLASS_EXPERIENCE_STANDARD.md"
        text = standard.read_text(encoding="utf-8")
        for phrase in ("Core Feel", "Accessibility", "Dashboard Rules", "Mobile Rules", "Proof Standard"):
            self.assertIn(phrase, text)
