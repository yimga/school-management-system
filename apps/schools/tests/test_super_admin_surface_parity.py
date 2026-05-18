"""
Operator surface IA: spine links, super-first pairs, and HTTP strip rendering.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.super_admin_paired_surfaces import (
    SUPER_FIRST_PAIRED_SPECS,
    build_operator_surface_ia_context,
    build_surface_parity_matrix,
    resolve_bridge_key_for_super_view,
)


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.manager_urls")
class SuperAdminSurfaceParityTests(TestCase):
    def setUp(self):
        self.host = "manager.runmycampus.com"
        User = get_user_model()
        self.user = User.objects.create_user(
            username="surface_ia_ops",
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

    def test_context_processor_on_super_and_admin(self):
        for path in ("/super/", "/admin/"):
            request = self.client.get(path, HTTP_HOST=self.host).wsgi_request
            request.user = self.user
            ctx = build_operator_surface_ia_context(request)
            self.assertTrue(ctx["RMC_OPERATOR_SURFACE_IA"], path)
            self.assertGreaterEqual(len(ctx["RMC_OPERATOR_SURFACE_SPINE"]), 4, path)

    def test_super_schools_list_shows_admin_bridge_chip(self):
        response = self.client.get(
            reverse("super:schools_list"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertContains(response, "Open platform admin")

    def test_admin_schools_changelist_shows_operator_view_chip(self):
        response = self.client.get(
            reverse("admin:schools_school_changelist"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertContains(response, "Open operator view")

    def test_manager_admin_uses_control_plane_sidebar_chrome(self):
        for path in ("/admin/", reverse("admin:schools_school_changelist")):
            response = self.client.get(path, HTTP_HOST=self.host)
            self.assertEqual(response.status_code, 200, path)
            html = response.content.decode()
            self.assertIn('id="cpSidebarNav"', html, path)
            self.assertIn("admin-cp-unified-page", html, path)
            self.assertIn("data-rmc-admin-cp-unified", html, path)
            self.assertIn("data-shell-nav-bridge=\"manager-operator\"", html, path)

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

    def test_admin_marketplace_changelist_shows_operator_view_chip(self):
        response = self.client.get(
            reverse(
                "admin:integrations_marketplace_marketplaceapp_changelist"
            ),
            HTTP_HOST=self.host,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertContains(response, "Open operator view")

    def test_super_first_specs_with_bridge_keys_are_registered(self):
        from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES

        for spec in SUPER_FIRST_PAIRED_SPECS:
            bridge_key = (spec.get("bridge_key") or "").strip()
            if not bridge_key:
                continue
            with self.subTest(slug=spec["slug"]):
                self.assertIn(bridge_key, PLATFORM_ADMIN_BRIDGES)
