"""
Operator surface IA: spine links, super-first pairs, and HTTP strip rendering.
"""

import os
import uuid
from unittest.mock import patch

from apps.accounts.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.schools.super_admin_paired_surfaces import (
    SUPER_FIRST_PAIRED_SPECS,
    build_operator_surface_ia_context,
    build_operator_surface_spine,
    build_surface_parity_matrix,
    resolve_bridge_key_for_super_view,
)


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
)
class SuperAdminSurfaceParityTests(TestCase):
    def setUp(self):
        self._mt_env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self._mt_env.start()
        self.host = "manager.runmycampus.com"
        self.user = User.objects.create_user(
            username=f"surface_ia_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_surface_parity_matrix_is_green(self):
        matrix = build_surface_parity_matrix()
        self.assertTrue(matrix["spine_ok"], matrix)
        self.assertTrue(matrix["pairs_ok"], matrix)
        self.assertTrue(matrix["bindings_ok"], matrix)
        self.assertTrue(matrix["browser_probes_ok"], matrix)

    def test_context_processor_shows_workspace_nav_on_super_not_admin(self):
        super_request = self.client.get("/super/", HTTP_HOST=self.host).wsgi_request
        super_request.user = self.user
        super_ctx = build_operator_surface_ia_context(super_request)
        self.assertTrue(super_ctx["RMC_OPERATOR_SURFACE_IA"])
        self.assertTrue(super_ctx["RMC_OPERATOR_SURFACE_STRIP_VISIBLE"])
        self.assertGreaterEqual(len(super_ctx["RMC_OPERATOR_SURFACE_SPINE"]), 4)

        admin_request = self.client.get("/admin/", HTTP_HOST=self.host).wsgi_request
        admin_request.user = self.user
        admin_ctx = build_operator_surface_ia_context(admin_request)
        self.assertTrue(admin_ctx["RMC_OPERATOR_SURFACE_IA"])
        self.assertFalse(admin_ctx["RMC_OPERATOR_SURFACE_STRIP_VISIBLE"])
        self.assertGreaterEqual(len(admin_ctx["RMC_OPERATOR_SURFACE_SPINE"]), 4)
        self.assertEqual(admin_ctx["RMC_OPERATOR_PAIRED_LINKS"], [])

    def test_workspace_spine_links_carry_icons(self):
        request = self.client.get("/super/", HTTP_HOST=self.host).wsgi_request
        request.user = self.user
        spine = build_operator_surface_spine(request)
        self.assertTrue(all(link.icon for link in spine))

    def test_workspace_spine_exactly_one_active_on_super_dashboard(self):
        request = self.client.get("/super/", HTTP_HOST=self.host).wsgi_request
        request.user = self.user
        spine = build_operator_surface_spine(request)
        active = [link for link in spine if link.active]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].link_id, "super_dashboard")

    def test_workspace_spine_no_spine_active_on_nested_super_list(self):
        request = self.client.get(
            reverse("super:schools_list"), HTTP_HOST=self.host
        ).wsgi_request
        request.user = self.user
        spine = build_operator_surface_spine(request)
        self.assertFalse(any(link.active for link in spine))

    def test_super_dashboard_includes_horizontal_nav_rail_stylesheet(self):
        response = self.client.get("/super/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-horizontal-nav-rail.css")
        self.assertContains(response, 'data-rmc-footer-surface="operator-compact"')
        self.assertContains(response, "rmc-manager-login-footer")
        self.assertNotContains(response, "mkt-footer-command")
        self.assertNotContains(response, "mkt-footer-newsletter")

    def test_super_schools_list_shows_admin_bridge_chip(self):
        response = self.client.get(
            reverse("super:schools_list"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertContains(response, "cp-primary-nav__pill")
        self.assertContains(response, "Open platform admin")

    def test_admin_schools_changelist_has_dropdown_not_strip(self):
        response = self.client.get(
            reverse("admin:schools_school_changelist"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-operator-workspace-dropdown")
        self.assertNotContains(response, "rmc-operator-workspace-nav")
        self.assertNotContains(response, "data-rmc-operator-surface-strip")

    def test_manager_admin_login_public_chrome(self):
        response = Client().get("/authentication/login/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-footer-surface=\"operator-compact\"")
        self.assertContains(response, "rmc-manager-login-footer")
        self.assertNotContains(response, "mkt-footer-command")
        self.assertContains(response, "Platform status")
        self.assertContains(response, "Find campus")
        self.assertContains(response, "rmc-footer-surfaces.css")

    def test_admin_waive_subscription_hides_workspace_strip(self):
        school = School.objects.create(
            name="Sweep Waive School",
            slug="sweep-waive-school",
            subdomain="sweep-waive-school",
        )
        url = reverse("admin:schools_school_waive_form")
        response = self.client.get(f"{url}?ids={school.pk}", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-operator-workspace-dropdown")
        self.assertNotContains(response, "rmc-operator-workspace-nav")
        self.assertNotContains(response, "data-rmc-operator-surface-strip")

    def test_manager_admin_uses_platform_admin_sidebar(self):
        for path in ("/admin/", reverse("admin:schools_school_changelist")):
            response = self.client.get(path, HTTP_HOST=self.host)
            self.assertEqual(response.status_code, 200, path)
            html = response.content.decode()
            self.assertIn('id="cpSidebarNav"', html, path)
            self.assertIn("admin-cp-unified-page", html, path)
            self.assertIn("data-rmc-admin-cp-unified", html, path)
            self.assertIn('data-shell-nav-family="platform-admin"', html, path)
            self.assertIn("data-rmc-platform-admin-sidebar", html, path)
            self.assertIn("admin-sidebar-all-apps", html, path)
            self.assertNotIn("cp-nav-group-toggle", html, path)
            self.assertNotIn('data-shell-nav-family="control-plane"', html, path)

    def test_manager_admin_index_renders_backoffice_content(self):
        response = self.client.get("/admin/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("cp-admin-index", html)
        self.assertIn("Platform Backoffice", html)
        self.assertIn('id="cp-main-content"', html)

    def test_manager_super_and_admin_share_operator_topbar(self):
        super_resp = self.client.get("/super/", HTTP_HOST=self.host)
        admin_resp = self.client.get("/admin/", HTTP_HOST=self.host)
        self.assertEqual(super_resp.status_code, 200)
        self.assertEqual(admin_resp.status_code, 200)
        for marker in ("id=\"cpSearchInput\"", "cp-topbar-theme-toggle", "data-shell-nav-bridge=\"manager-operator\""):
            self.assertIn(marker, super_resp.content.decode())
            self.assertIn(marker, admin_resp.content.decode())

    def test_configuration_center_shows_surface_strip(self):
        response = self.client.get(
            reverse("configuration:center"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")

    def test_marketplace_governance_shows_admin_bridge_chip(self):
        response = self.client.get(
            reverse("super:marketplace_governance"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertContains(response, "Open platform admin")

    def test_security_hub_shows_admin_bridge_chip(self):
        response = self.client.get(
            reverse("super:security_hub"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertContains(response, "Open platform admin")

    def test_nested_marketplace_path_resolves_bridge_key(self):
        self.assertEqual(
            resolve_bridge_key_for_super_view(
                "marketplace_install_impact_preview",
                "/super/marketplace/apps/install-impact-preview/",
            ),
            "marketplace_apps",
        )

    def test_admin_marketplace_changelist_hides_workspace_nav(self):
        response = self.client.get(
            reverse(
                "admin:integrations_marketplace_marketplaceapp_changelist"
            ),
            HTTP_HOST=self.host,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "rmc-operator-workspace-nav")

    def test_super_first_specs_with_bridge_keys_are_registered(self):
        from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES

        for spec in SUPER_FIRST_PAIRED_SPECS:
            bridge_key = (spec.get("bridge_key") or "").strip()
            if not bridge_key:
                continue
            with self.subTest(slug=spec["slug"]):
                self.assertIn(bridge_key, PLATFORM_ADMIN_BRIDGES)
