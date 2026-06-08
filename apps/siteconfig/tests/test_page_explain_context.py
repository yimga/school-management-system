"""Page explain strip context — operator + tenant catalog wiring."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.siteconfig.page_explain import build_page_explain_context, build_field_manifest
from apps.siteconfig.ui_field_help import catalog_entry_count
from apps.siteconfig.ui_route_help import resolve_route_help


class CatalogSizeTests(SimpleTestCase):
    def test_catalog_meets_500x_minimum(self):
        self.assertGreaterEqual(catalog_entry_count(), 500)


class PageExplainContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="explain-tester",
            password="Test1234!",
            is_staff=True,
        )

    def _request(self, path="/", host_kind="tenant"):
        request = self.factory.get(path)
        request.user = self.user
        request.public_host_kind = host_kind
        request.resolver_match = None
        return request

    def test_anonymous_returns_empty(self):
        request = self.factory.get("/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        ctx = build_page_explain_context(request)
        self.assertEqual(ctx, {})

    def test_authenticated_tenant_has_manifest_and_help(self):
        request = self._request("/authentication/backend/", host_kind="tenant")
        ctx = build_page_explain_context(request)
        self.assertTrue(ctx.get("rmc_page_explain_enabled"))
        self.assertIn("rmc_page_help", ctx)
        self.assertIsInstance(ctx.get("rmc_page_field_manifest"), list)

    def test_authenticated_operator_surface(self):
        request = self._request("/super/", host_kind="manager")
        ctx = build_page_explain_context(request)
        self.assertTrue(ctx.get("rmc_page_explain_enabled"))
        help_payload = ctx["rmc_page_help"]
        self.assertEqual(help_payload.get("surface"), "operator")

    def test_route_override_email_configure(self):
        request = self._request("/super/schoolops/email/")
        request.public_host_kind = "manager"
        request.resolver_match = type(
            "M",
            (),
            {
                "namespace": "schoolops",
                "url_name": "email_configure",
                "view_name": "schoolops:email_configure",
            },
        )()
        help_payload = resolve_route_help(request)
        self.assertIn("SMTP", str(help_payload.get("body", "")))
        manifest = build_field_manifest(request, help_payload)
        fields = {row["field"] for row in manifest}
        self.assertIn("smtp_host", fields)
