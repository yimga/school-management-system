from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class BillingAppleClassUXTests(SimpleTestCase):
    def test_billing_surfaces_show_usage_and_external_psp_honesty(self):
        paths = [
            ROOT / "templates" / "schools" / "billing_dashboard.html",
            ROOT / "templates" / "finance" / "dashboard.html",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("data-apple-class-billing-ux", text)
                self.assertIn("apple_class_data_quality_meter.html", text)
                self.assertIn("Usage Meter", text)
                self.assertIn("PSP", text)
                self.assertNotIn("live payments certified", text.lower())
