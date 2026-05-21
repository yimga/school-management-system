"""Template + URL contract for School Studio (no heavy HTTP DB)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

ROOT = Path(__file__).resolve().parent.parent.parent.parent


class TenantStudioTemplateContractTests(SimpleTestCase):
    def test_hub_template_has_required_markers(self):
        text = (ROOT / "templates/siteconfig/tenant_studio_hub.html").read_text(
            encoding="utf-8"
        )
        for needle in (
            'data-rmc-tenant-studio-launch-path="1"',
            'data-rmc-tenant-studio-readiness="1"',
            "data-rmc-tenant-studio-primary-action",
            "data-rmc-tenant-studio-ai-guidance",
            "data-rmc-ai-guided",
            "data-ai-contextual-insight",
        ):
            self.assertIn(needle, text, msg=needle)

    def test_onboarding_body_links_hub(self):
        body = (ROOT / "templates/siteconfig/partials/onboarding_body.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("school_studio", body)
        self.assertIn('data-rmc-tenant-studio-launch-path="1"', body)

    def test_tenant_url_names_resolve(self):
        names = (
            "school_studio",
            "school_studio_setup",
            "school_studio_readiness",
            "school_studio_migration",
            "school_studio_help",
            "school_studio_launch",
        )
        for name in names:
            try:
                path = reverse(name, urlconf="config.tenant_urls")
            except NoReverseMatch as exc:
                self.fail(f"{name}: {exc}")
            self.assertTrue(path.startswith("/school/studio"), msg=f"{name} -> {path}")
