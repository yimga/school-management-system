from django.test import SimpleTestCase

from apps.brand_experience.control_plane_brand_vars import control_plane_brand_css_vars


class ControlPlaneBrandVarsTests(SimpleTestCase):
    def test_emits_operator_css_variables(self):
        css = control_plane_brand_css_vars(
            primary_color="#112233",
            accent_color="#aabb00",
        )
        self.assertIn("--rmc-operator-primary:#112233", css)
        self.assertIn("--rmc-operator-accent:#aabb00", css)
        self.assertIn("body.control-plane-shell", css)
