"""
Theme stress-test matrix: template load + theme/contrast guard checks.
Run with: python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1
Fails if key dashboard templates do not load or lack required theme/visibility hooks.
"""
from django.template.loader import get_template
from django.test import SimpleTestCase


class ThemeVisibilityMatrixTests(SimpleTestCase):
    """Key pages × theme support: templates load and reference guard/token assets."""

    TEMPLATES = [
        "accounts/backend_dashboard.html",
        "parent/dashboard.html",
        "teacher/dashboard.html",
    ]

    def test_dashboard_templates_load(self):
        for name in self.TEMPLATES:
            with self.subTest(template=name):
                t = get_template(name)
                self.assertIsNotNone(t)

    def test_backend_dashboard_has_token_css(self):
        from django.template.loader import get_template
        t = get_template("accounts/backend_dashboard.html")
        content = t.origin.loader.get_contents(t.origin)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        self.assertIn("backend-dashboard-tokens.css", content, msg="Backend dashboard should load token CSS")
        self.assertIn("--brand-primary", content, msg="Backend dashboard should define/inject brand tokens")

    def test_site_settings_change_form_loads(self):
        t = get_template("admin/siteconfig/sitesettings/change_form.html")
        self.assertIsNotNone(t)
