"""
Stage 3: white-label token hydration, cascade, sanitization (no CLS / XSS vectors).
"""

from __future__ import annotations

from pathlib import Path

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.brand_experience.resolvers import get_unified_theme_tokens
from apps.siteconfig.brand_guard_runtime import guard_brand_dict
from apps.siteconfig.svg_sanitize import sanitize_svg_bytes
from apps.schools.models import School


class SevenLayerCascadeDocumentationTests(SimpleTestCase):
    """Document 7-layer cascade files exist (RuntimeDefaults → CSS vars)."""

    def test_cascade_source_files_present(self):
        root = Path(__file__).resolve().parents[3]
        required = (
            "apps/platform_runtime/runtime_defaults_first_class.py",
            "apps/siteconfig/domain_ownership.py",
            "templates/partials/rmc_theme_meta.html",
            "static/js/theme-preference-bootstrap.js",
            "static/css/design-tokens.css",
        )
        for rel in required:
            self.assertTrue((root / rel).is_file(), rel)

    def test_theme_meta_references_runtime_defaults_fields(self):
        root = Path(__file__).resolve().parents[3]
        meta = (root / "templates/partials/rmc_theme_meta.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("SITE.neutral_palette", meta)
        self.assertIn("rmc-aesthetic-profile", meta)

    def test_theme_bootstrap_never_writes_system_to_data_theme(self):
        root = Path(__file__).resolve().parents[3]
        js = (root / "static/js/theme-preference-bootstrap.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-theme-preference", js)
        self.assertNotIn('setAttribute("data-theme", "system")', js)
        self.assertNotIn("setAttribute('data-theme', 'system')", js)


class BrandGuardAndSanitizeTests(SimpleTestCase):
    def test_guard_brand_dict_remediates_low_contrast_primary(self):
        brand = {"primary_color": "#ffff00", "accent_color": "#198754"}
        out, adjusted = guard_brand_dict(brand, effective_surface="tenant")
        self.assertTrue(adjusted or out.get("primary_color") != "#ffff00")
        self.assertIn("primary_color", out)

    def test_svg_sanitize_strips_script(self):
        evil = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<script>alert(1)</script>"
            b'<circle r="10"/></svg>'
        )
        out = sanitize_svg_bytes(evil)
        self.assertNotIn(b"<script", out.lower())
        self.assertNotIn(b"alert", out)

    def test_svg_sanitize_accepts_clean_logo(self):
        clean = (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            b'<rect width="10" height="10" fill="#4F46E5"/></svg>'
        )
        out = sanitize_svg_bytes(clean)
        self.assertIn(b"<svg", out)
        self.assertNotIn(b"<script", out.lower())


@override_settings(ALLOWED_HOSTS=["*"])
class TenantBrandingContextTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Brand Hydration School",
            slug="brand-hydration",
            subdomain="brand-hydration",
            is_active=True,
        )

    def test_unified_theme_tokens_returns_dict_for_school(self):
        tokens = get_unified_theme_tokens(school=self.school)
        self.assertIsInstance(tokens, dict)

    def test_context_processor_exposes_site_colors_when_school_set(self):
        from apps.siteconfig.context_processors import site_settings

        factory = RequestFactory()
        request = factory.get("/", HTTP_HOST="brand-hydration.runmycampus.com")
        request.school = self.school
        request.public_host_kind = None
        ctx = site_settings(request)
        self.assertIn("SITE_PRIMARY_COLOR", ctx)
        self.assertTrue(ctx.get("SITE_PRIMARY_COLOR"))
