"""Template + URL contract for School Studio (no heavy HTTP DB)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.siteconfig.tests._template_nodes import assert_markup

ROOT = Path(__file__).resolve().parent.parent.parent.parent

HUB = ROOT / "templates/siteconfig/tenant_studio_hub.html"
ONBOARDING_BODY = ROOT / "templates/siteconfig/partials/onboarding_body.html"


class TenantStudioTemplateContractTests(SimpleTestCase):
    def test_hub_template_has_required_markers(self):
        # All six are emitted markup, so ask the ENGINE what the hub actually
        # renders instead of what its bytes contain: every one of them survived
        # wrapping the whole file in a {% comment %} before this change.
        assert_markup(
            self,
            HUB,
            'data-rmc-tenant-studio-launch-path="1"',
            'data-rmc-tenant-studio-readiness="1"',
            "data-rmc-tenant-studio-primary-action",
            "data-rmc-tenant-studio-ai-guidance",
            "data-rmc-ai-guided",
            "data-ai-contextual-insight",
        )

    def test_onboarding_body_links_hub(self):
        body = (ROOT / "templates/siteconfig/partials/onboarding_body.html").read_text(
            encoding="utf-8"
        )
        # "school_studio" is a {% url %} NAME -- template code -- and the partial
        # cannot render standalone because that route is tenant-only
        # (NoReverseMatch on the default urlconf). It stays a source read.
        self.assertIn("school_studio", body)
        assert_markup(self, ONBOARDING_BODY, 'data-rmc-tenant-studio-launch-path="1"')

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
