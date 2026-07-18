"""Unit tests for ThemePack.palette.admin_dashboard → --admin-* CSS emitter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from apps.siteconfig.admin_palette_css import (
    admin_dashboard_palette_css_vars,
    extract_admin_dashboard_palette,
)


class AdminPaletteCssEmitterTests(TestCase):
    def test_emits_admin_custom_properties_from_palette_json(self):
        palette = {
            "primary": "#f7a53a",
            "accent": "#ff654f",
            "accent_light": "#ffb088",
            "dashboard_bg": "#fff8f1",
            "surface": "#ffffff",
            "border": "rgba(255,101,79,0.14)",
            "border_strong": "rgba(247,165,58,0.28)",
            "text": "#1c1917",
            "muted": "#78716c",
            "subtle": "#57534e",
            "role_admin": "#ff654f",
            "role_student": "#f7a53a",
            "role_teacher": "#35d399",
        }

        css = admin_dashboard_palette_css_vars(palette)

        self.assertIn("--admin-dashboard-bg: #fff8f1;", css)
        self.assertIn("--admin-surface: #ffffff;", css)
        self.assertIn("--admin-primary: #f7a53a;", css)
        self.assertIn("--admin-accent: #ff654f;", css)
        self.assertIn("--admin-role-admin: #ff654f;", css)
        self.assertIn("--admin-role-student: #f7a53a;", css)
        self.assertIn("--admin-role-teacher: #35d399;", css)
        self.assertIn("--brand-primary: #f7a53a;", css)
        self.assertIn("--school-primary: #f7a53a;", css)

    def test_rejects_css_injection_payloads(self):
        css = admin_dashboard_palette_css_vars(
            {
                "primary": "#112233; } body { background: url(evil)",
                "surface": "red",
                "dashboard_bg": "rgba(1,2,3,0.5)",
            }
        )
        self.assertNotIn("url(", css)
        self.assertNotIn("body", css)
        self.assertIn("--admin-surface: red;", css)
        self.assertIn("--admin-dashboard-bg: rgba(1,2,3,0.5);", css)
        self.assertNotIn("--admin-primary:", css)

    def test_extract_reads_admin_dashboard_nested_dict(self):
        pack = SimpleNamespace(
            palette={"admin_dashboard": {"primary": "#111111", "surface": "#ffffff"}}
        )
        extracted = extract_admin_dashboard_palette(pack)
        self.assertEqual(extracted["primary"], "#111111")
        self.assertEqual(extract_admin_dashboard_palette(None), {})
        self.assertEqual(
            extract_admin_dashboard_palette(SimpleNamespace(palette={})), {}
        )

    def test_spec_palettes_are_in_curated_catalog_source(self):
        seed_path = Path(
            "apps/siteconfig/management/commands/seed_admin_dashboard_palettes.py"
        )
        source = seed_path.read_text(encoding="utf-8")
        for slug in (
            "admin-sunrise-campus",
            "admin-scholar-grove",
            "admin-coastal-clarity",
            "admin-berry-leadership",
            "admin-accessible-midnight",
        ):
            self.assertIn(f'"{slug}"', source)

    def test_as_root_block_wraps_declarations(self):
        css = admin_dashboard_palette_css_vars(
            {"primary": "#abcdef"}, as_root_block=True
        )
        self.assertTrue(css.startswith(":root {"))
        self.assertIn("--admin-primary: #abcdef;", css)
        self.assertTrue(css.endswith("}"))

    def test_templates_emit_palette_css_vars(self):
        admin_base = Path("templates/admin/base_site.html").read_text(encoding="utf-8")
        backend = Path("templates/backend_base_tenant.html").read_text(encoding="utf-8")
        self.assertIn("ADMIN_DASHBOARD_PALETTE_CSS_VARS", admin_base)
        self.assertIn("ADMIN_DASHBOARD_PALETTE_CSS_VARS", backend)
        self.assertIn("admin-brand-resolved-tokens", admin_base)
