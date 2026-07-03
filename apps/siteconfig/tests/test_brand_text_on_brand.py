"""Wave 3-tail: adaptive --text-on-brand in the tenant brand cascade.

The ~48 sites that render white-on-brand text consume var(--text-on-brand, #fff);
until now the variable was never set, so a light school brand (yellow, pale green)
washed the text out. brand_css_vars now emits an adaptive on-brand ink — dark on a
light brand, light on a dark brand — so those headers stay readable for every
school without touching a single template.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.siteconfig.branding import brand_css_vars


class BrandTextOnBrandTests(SimpleTestCase):
    def test_dark_brand_gets_light_ink(self):
        css = brand_css_vars({"primary_color": "#4f46e5"})  # indigo
        self.assertIn("--text-on-brand: #f1f5f9;", css)

    def test_light_brand_gets_dark_ink(self):
        css = brand_css_vars({"primary_color": "#facc15"})  # yellow
        self.assertIn("--text-on-brand: #0f172a;", css)

    def test_white_brand_gets_dark_ink(self):
        css = brand_css_vars({"tokens": {"primary": "#ffffff"}})
        self.assertIn("--text-on-brand: #0f172a;", css)

    def test_no_primary_emits_no_var(self):
        self.assertNotIn("--text-on-brand", brand_css_vars({}))
