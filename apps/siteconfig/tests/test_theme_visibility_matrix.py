"""
Theme stress-test matrix: template load + theme/contrast guard checks.
Run with: python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1
Fails if key dashboard templates do not load or lack required theme/visibility hooks.
"""
import os

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
        t = get_template("accounts/backend_dashboard.html")
        content = t.origin.loader.get_contents(t.origin)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        self.assertIn("--brand-primary", content, msg="Backend dashboard should define/inject brand tokens")
        # Token CSS file or inline tokens
        has_tokens = "backend-dashboard-tokens.css" in content or "--admin-" in content
        self.assertTrue(has_tokens, msg="Backend dashboard should load token CSS or define --admin-* tokens")

    def test_site_settings_change_form_loads(self):
        t = get_template("admin/siteconfig/sitesettings/change_form.html")
        self.assertIsNotNone(t)

    def test_backend_token_or_brand_primary_present(self):
        """Backend dashboard or its assets should reference --brand-primary or token contract."""
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        candidates = [
            os.path.join(root, "static", "css", "backend-dashboard-tokens.css"),
            os.path.join(root, "static", "css", "backend-dashboard-v2.css"),
            os.path.join(root, "static", "css", "backend-dashboard-extras.css"),
            os.path.join(root, "templates", "accounts", "backend_dashboard.html"),
        ]
        found = False
        for path in candidates:
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if "--brand-primary" in content or "--admin-" in content or "var(--" in content:
                found = True
                break
        self.assertTrue(found, "Expected backend token CSS (--brand-primary or --admin-*) in dashboard assets")
