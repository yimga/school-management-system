"""Sandbox embed URL registry for TOP_15 catalog apps."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from apps.marketplace.capability_contract import (
    TOP_15_APP_SLUGS,
    enrich_manifest_capability_bindings,
)
from apps.marketplace.models import MarketplaceApp
from apps.marketplace.sandbox_embed_registry import (
    registry_validation_errors,
    resolve_sandbox_iframe_src,
    widgets_dict_for_slug,
)
from apps.marketplace.views import sandbox_embed
from apps.marketplace.services import install_app
from apps.schools.models import School


class SandboxEmbedRegistryTests(TestCase):
    def test_registry_covers_top_15_with_reversible_urls(self):
        self.assertEqual(registry_validation_errors(), [])

    def test_enrich_manifest_adds_url_name_widgets(self):
        manifest = enrich_manifest_capability_bindings(
            "transport-bus-tracker",
            {"scopes": ["transport"], "widgets": []},
        )
        widgets = manifest.get("widgets") or {}
        self.assertIn("transport_ops_preview", widgets)
        self.assertEqual(
            widgets["transport_ops_preview"].get("url_name"),
            "accounts:ops_transport",
        )

    def test_every_top_15_slug_has_widget_entry(self):
        for slug in TOP_15_APP_SLUGS:
            widgets = widgets_dict_for_slug(slug)
            self.assertTrue(widgets, msg=slug)
            primary = next(iter(widgets.values()))
            self.assertTrue(primary.get("url_name"), msg=slug)

    def test_full_catalog_has_embed_widget(self):
        from apps.marketplace.management.commands.seed_marketplace_apps import (
            FIRST_PARTY_APPS,
        )

        for app_def in FIRST_PARTY_APPS:
            slug = app_def["slug"]
            widgets = widgets_dict_for_slug(slug)
            self.assertTrue(widgets, msg=slug)
            self.assertTrue(
                next(iter(widgets.values())).get("url_name"),
                msg=slug,
            )


class SandboxEmbedViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("seed_marketplace_apps", verbosity=0)

    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(
            name="Sandbox Embed School",
            slug="sandbox-embed-school",
            subdomain="sandbox-embed-school",
            is_active=True,
            features={"transport": True},
        )
        self.user = User.objects.create_user(
            username="sandbox-embed-admin",
            password="Test1234!",
            role="ADMIN",
        )
        self.app = MarketplaceApp.objects.get(slug="transport-bus-tracker")
        self.installation = install_app(
            self.school,
            self.app,
            installed_by=self.user,
            install_phase="sandbox",
            skip_compatibility=True,
        )
        manifest = enrich_manifest_capability_bindings(
            self.app.slug,
            self.app.manifest or {},
        )
        self.installation.widget_config = manifest.get("widgets") or {}
        self.installation.save(update_fields=["widget_config"])

    def test_resolve_sandbox_iframe_src_for_transport(self):
        src = resolve_sandbox_iframe_src(
            app_slug="transport-bus-tracker",
            widget_config=self.installation.widget_config,
            widget_id="transport_ops_preview",
        )
        self.assertIsNotNone(src)
        self.assertIn("ops/transport", src)

    def test_sandbox_embed_view_renders_iframe_src(self):
        request = RequestFactory().get(
            "/siteconfig/app-sandbox/",
            {"app_slug": "transport-bus-tracker"},
        )
        request.user = self.user
        request.school = self.school
        response = sandbox_embed(request)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("iframe", body)
        self.assertIn("ops/transport", body)
        self.assertNotIn('src=""', body)
        self.assertNotIn("about:blank", body)
