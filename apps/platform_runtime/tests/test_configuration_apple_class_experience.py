from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class ConfigurationAppleClassExperienceTests(SimpleTestCase):
    def test_configuration_console_has_grouped_depth_model(self):
        text = (ROOT / "templates" / "platform_runtime" / "configuration_center.html").read_text(encoding="utf-8")
        for token in (
            "data-apple-class-configuration-console",
            "data-apple-class-configuration-groups",
            "Operating Models",
            "Runtime Governance",
            "Trust + Money",
            "apple_class_data_quality_meter.html",
            "Browser proof pending",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
