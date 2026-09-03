from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires


ROOT = Path(__file__).resolve().parents[3]
CONFIGURATION_CENTER = ROOT / "templates" / "platform_runtime" / "configuration_center.html"


class ConfigurationAppleClassExperienceTests(SimpleTestCase):
    def test_configuration_console_has_grouped_depth_model(self):
        template = (ROOT / "templates" / "platform_runtime" / "configuration_center.html").read_text(encoding="utf-8")
        nav = (ROOT / "apps" / "platform_runtime" / "operational_center_nav.py").read_text(encoding="utf-8")
        frame = (ROOT / "templates" / "components" / "rmc_operational_center_frame.html").read_text(encoding="utf-8")
        # The frame was split into an outer wrapper that {% include %}s an _inner
        # partial; the depth-model data attributes moved into the inner file.
        frame_inner = (ROOT / "templates" / "components" / "rmc_operational_center_frame_inner.html").read_text(encoding="utf-8")
        bundle = f"{template}\n{frame}\n{frame_inner}\n{nav}"
        # The token sweep below runs over a CONCATENATION of four files, so a
        # token found there says nothing about which file emits it -- and every
        # one of them survives that file being commented out. Aimed at
        # configuration_center.html, the template this case is bound to: the
        # console scope is markup it must emit, and the frame and the data
        # quality meter are {% include %}s it must really pull in.
        assert_markup(self, CONFIGURATION_CENTER, "data-apple-class-configuration-console")
        assert_wires(
            self,
            CONFIGURATION_CENTER,
            "components/rmc_operational_center_frame.html",
            "components/apple_class_data_quality_meter.html",
        )
        for token in (
            "data-apple-class-configuration-console",
            "data-rmc-operational-center-frame",
            "data-rmc-ops-nav-grid",
            "data-apple-class-configuration-groups",
            "configuration_nav_groups",
            "apple_class_data_quality_meter.html",
            "module.readiness_score",
            "module.readiness_label",
        ):
            with self.subTest(token=token):
                self.assertIn(token, bundle)
        for label in ("Operating Models", "Runtime Governance", "Trust + Money"):
            with self.subTest(label=label):
                self.assertIn(label, nav)
