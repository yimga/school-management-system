"""
Tests for high-end admin (Configuration Engine) experience: superadmin-only, no tenant comingling.
"""

from pathlib import Path

from django.test import RequestFactory, TestCase
from django.template.loader import get_template

from config.admin import admin_site
from apps.siteconfig.unfold_dashboard import (
    dashboard_callback,
    ADMIN_PLATFORM_PRIMARY,
    ADMIN_PLATFORM_ACCENT,
)


class AdminLoginTemplateTests(TestCase):
    """Admin uses high-end login template and superadmin-only copy."""

    def test_admin_site_uses_high_end_login_template(self):
        self.assertEqual(admin_site.login_template, "auth/admin_login.html")

    def test_admin_login_template_exists_and_loads(self):
        t = get_template("auth/admin_login.html")
        self.assertIsNotNone(t)

    def test_admin_login_template_has_no_tenant_copy(self):
        """Admin login must not contain tenant-facing or school-specific wording."""
        t = get_template("auth/admin_login.html")
        path = (
            Path(t.origin.name)
            if getattr(t, "origin", None) and getattr(t.origin, "name", None)
            else Path(__file__).resolve().parent.parent.parent.parent
            / "templates"
            / "auth"
            / "admin_login.html"
        )
        self.assertTrue(path.exists(), f"Template not found: {path}")
        content = path.read_text(encoding="utf-8", errors="replace")
        # Superadmin-only: no tenant/school/staff-account/powerhouse tagline
        self.assertNotIn("POWERHOUSE", content)
        self.assertNotIn("staff account", content)
        self.assertIn("superuser", content)
        self.assertIn("RunMyCampus Manager", content)


class UnfoldDashboardCallbackAdminTests(TestCase):
    """When path is /admin/, dashboard callback must not use request.school."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_admin_path_gets_platform_branding_only(self):
        request = self.factory.get("/admin/")
        request.path = "/admin/"
        request.school = type(
            "School",
            (),
            {
                "logo_url": "/tenant.png",
                "primary_color": "#ff0000",
                "accent_color": "#00ff00",
            },
        )()
        context = {}
        result = dashboard_callback(request, context)
        self.assertEqual(result["unfold_school_logo_url"], "")
        self.assertEqual(result["unfold_school_primary_color"], ADMIN_PLATFORM_PRIMARY)
        self.assertEqual(result["unfold_school_accent_color"], ADMIN_PLATFORM_ACCENT)

    def test_admin_login_path_also_gets_platform_branding(self):
        request = self.factory.get("/admin/login/")
        request.path = "/admin/login/"
        request.school = type("School", (), {"logo_url": "/x.png"})()
        context = {}
        result = dashboard_callback(request, context)
        self.assertEqual(result["unfold_school_logo_url"], "")
        self.assertEqual(result["unfold_school_primary_color"], ADMIN_PLATFORM_PRIMARY)
