from django.test import TestCase


class MarketingProductPagePhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        from pathlib import Path

        from django.conf import settings

        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "schools"
            / "marketing_product_page.html"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn('href="#mkt-product-hero"', text)
        self.assertIn('id="mkt-product-hero"', text)
