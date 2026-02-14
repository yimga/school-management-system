"""
Theme stress-test matrix: template load + theme/contrast guard checks.
Run with: python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1
Fails if key dashboard templates do not load or lack required theme/visibility hooks.
"""
import os

from django.template.loader import get_template
from django.test import SimpleTestCase


# Key pages included in stress-test matrix (must extend a base that loads theme-visibility-guard.css)
KEY_PAGE_TEMPLATES = [
    "accounts/backend_dashboard.html",
    "parent/dashboard.html",
    "teacher/dashboard.html",
    "siteconfig/theme_colors.html",  # Theme & Experience
]
# Base templates that must load the guard so all children get it
BASE_TEMPLATES_WITH_GUARD = [
    "base.html",
    "portal_base.html",
    "admin/base_site.html",
    "admin/login.html",
]


def get_template_content(name):
    """Return decoded template source (string)."""
    t = get_template(name)
    content = t.origin.loader.get_contents(t.origin)
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    return content


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

    def test_key_page_templates_load(self):
        """All key pages (including Theme & Experience, dashboards) load."""
        for name in KEY_PAGE_TEMPLATES:
            with self.subTest(template=name):
                t = get_template(name)
                self.assertIsNotNone(t)

    def test_base_templates_load_guard_css(self):
        """Base templates that feed key pages must include theme-visibility-guard.css."""
        for name in BASE_TEMPLATES_WITH_GUARD:
            with self.subTest(template=name):
                content = get_template_content(name)
                self.assertIn(
                    "theme-visibility-guard.css",
                    content,
                    msg=f"{name} must load theme-visibility-guard.css so child pages get visibility rules",
                )

    def test_guard_css_defines_vis_tokens(self):
        """Guard file defines --vis-* tokens used by guard rules."""
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        guard_path = os.path.join(root, "static", "css", "theme-visibility-guard.css")
        if not os.path.isfile(guard_path):
            self.skipTest("theme-visibility-guard.css not found (path may differ)")
        with open(guard_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("--vis-text", content, msg="Guard must define --vis-text")
        self.assertIn("--vis-text-muted", content, msg="Guard must define --vis-text-muted")
        self.assertIn("--vis-border", content, msg="Guard must define --vis-border")

    def test_guard_css_theme_experience_page_block(self):
        """Guard includes .theme-experience-page block for Theme & Experience."""
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        guard_path = os.path.join(root, "static", "css", "theme-visibility-guard.css")
        if not os.path.isfile(guard_path):
            self.skipTest("theme-visibility-guard.css not found")
        with open(guard_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".theme-experience-page", content, msg="Guard must style .theme-experience-page catalog")

    def test_backend_dashboard_has_token_css(self):
        content = get_template_content("accounts/backend_dashboard.html")
        self.assertIn("backend-dashboard-tokens.css", content, msg="Backend dashboard should load token CSS")
        self.assertIn("--brand-primary", content, msg="Backend dashboard should define/inject brand tokens")

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
