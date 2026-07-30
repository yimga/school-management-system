from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class ConfigurationAppleClassExperienceTests(SimpleTestCase):
    def test_configuration_console_has_grouped_depth_model(self):
        template = (ROOT / "templates" / "platform_runtime" / "configuration_center.html").read_text(encoding="utf-8")
        nav = (ROOT / "apps" / "platform_runtime" / "operational_center_nav.py").read_text(encoding="utf-8")
        frame = (ROOT / "templates" / "components" / "rmc_operational_center_frame.html").read_text(encoding="utf-8")
        # The frame was split into an outer wrapper that {% include %}s an _inner
        # partial; the depth-model data attributes moved into the inner file.
        frame_inner = (ROOT / "templates" / "components" / "rmc_operational_center_frame_inner.html").read_text(encoding="utf-8")
        bundle = f"{template}\n{frame}\n{frame_inner}\n{nav}"
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
