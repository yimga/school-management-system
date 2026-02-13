"""
Theme stress-test matrix: template load for key dashboards + backend token CSS.
Run: python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1
"""
import os

from django.template.loader import get_template
from django.test import SimpleTestCase


class ThemeVisibilityMatrixTests(SimpleTestCase):
    """Load key dashboard templates and assert backend token CSS is present."""

    def test_backend_dashboard_template_loads(self):
        t = get_template("accounts/backend_dashboard.html")
        self.assertIsNotNone(t)

    def test_backend_token_or_brand_primary_present(self):
        """Backend dashboard or its assets should reference --brand-primary or token contract."""
        # From apps/siteconfig/tests/ go up to project root (3 levels).
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
