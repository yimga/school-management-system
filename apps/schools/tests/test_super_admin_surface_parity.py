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
from apps.schools.tests.manager_client import bind_manager_session
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
        self.addCleanup(self._mt_env.stop)
        self.host = "manager.runmycampus.com"
        self.password = "testpass123"
        self.user = User.objects.create_user(
            username=f"surface_ia_{uuid.uuid4().hex[:8]}",
            password=self.password,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=self.host)
        self.client.force_login(self.user)
        bind_manager_session(self.client)

    def _manager_super_request(self, path: str):
        from django.test import RequestFactory
        from django.urls import resolve

        request = RequestFactory().get(path, HTTP_HOST=self.host)
        request.user = self.user
        request.public_host_kind = "manager"
        request.resolver_match = resolve(path)
        return request

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
        self.assertGreaterEqual(len(super_ctx["RMC_OPERATOR_SURFACE_SPINE"]), 3)

        admin_request = self.client.get("/admin/", HTTP_HOST=self.host).wsgi_request
        admin_request.user = self.user
        admin_ctx = build_operator_surface_ia_context(admin_request)
        self.assertTrue(admin_ctx["RMC_OPERATOR_SURFACE_IA"])
        self.assertTrue(admin_ctx["RMC_OPERATOR_SURFACE_STRIP_VISIBLE"])
        self.assertGreaterEqual(len(admin_ctx["RMC_OPERATOR_SURFACE_SPINE"]), 3)
        self.assertEqual(admin_ctx["RMC_OPERATOR_PAIRED_LINKS"], [])
        spine_labels = [link.label for link in admin_ctx["RMC_OPERATOR_SURFACE_SPINE"]]
        self.assertFalse(
            any("platform admin" in lbl.lower() for lbl in spine_labels),
            spine_labels,
        )

    def test_manager_admin_changelist_exposes_paired_operator_view(self):
        from django.test import RequestFactory
        from django.urls import resolve, reverse

        admin_url_name = "admin:integrations_marketplace_integration_changelist"
        path = reverse(admin_url_name)
        request = RequestFactory().get(path, HTTP_HOST=self.host)
        request.user = self.user
        request.public_host_kind = "manager"
        request.resolver_match = resolve(path)
        admin_ctx = build_operator_surface_ia_context(request)
        self.assertGreaterEqual(len(admin_ctx["RMC_OPERATOR_PAIRED_LINKS"]), 1)
        labels = [link.label for link in admin_ctx["RMC_OPERATOR_PAIRED_LINKS"]]
        self.assertTrue(any("operator" in lbl.lower() for lbl in labels))

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
        self.assertContains(response, "data-rmc-manager-operator-footer")
        self.assertNotContains(response, "mkt-footer-command")
        self.assertNotContains(response, "mkt-footer-newsletter")
        self.assertContains(response, "rmc-platform-chrome-premium.css")
        self.assertContains(response, "rmc-cp-chrome-scroll-polish.js")
        self.assertContains(response, "dashboard-topology-shell.css")
        self.assertContains(response, 'data-rmc-cp-scroll="document"')
        self.assertContains(response, 'data-rmc-control-plane-chrome="1"')
        self.assertNotContains(response, 'data-rmc-os-page-header="1"')
        html = response.content.decode()
        mcp_pos = html.rfind("manager-control-plane.css")
        chrome_pos = html.rfind("rmc-platform-chrome-layout.css")
        self.assertGreater(chrome_pos, mcp_pos)

    def test_super_dashboard_workspace_spine_omits_platform_admin(self):
        response = self.client.get("/super/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "rmc-operator-surface-strip")
        self.assertNotContains(response, "rmc-page-explain-strip")
        self.assertNotContains(response, "About this page")
        self.assertContains(response, 'id="rmc-world-globe-ai-guide"')
        self.assertNotContains(response, "Platform admin")
        self.assertNotContains(response, "Open platform admin")

        response = self.client.get(
            reverse("super:schools_list"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertContains(response, "cp-primary-nav__pill")
        self.assertNotContains(response, "Open platform admin")
        self.assertNotContains(response, "Platform admin")

    def test_admin_schools_changelist_shows_workspace_strip_and_paired_cta(self):
        response = self.client.get(
            reverse("admin:schools_school_changelist"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-operator-workspace-dropdown")
        self.assertNotContains(response, "rmc-operator-workspace-nav")
        self.assertContains(response, "data-rmc-operator-surface-strip")
        self.assertContains(response, "data-rmc-admin-steering-strip")

    def test_manager_admin_change_form_exposes_paired_operator_view(self):
        school = School.objects.create(
            name="Paired Change School",
            slug="paired-change-school",
            subdomain="paired-change-school",
        )
        url = reverse("admin:schools_school_change", args=[school.pk])
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-admin-changeform-head")
        self.assertContains(response, "data-rmc-operator-surface-strip")
        html = response.content.decode()
        self.assertTrue(
            "operator" in html.lower() or "control plane" in html.lower(),
            "change form should surface super-first paired CTA",
        )

    def test_admin_dashboard_redirects_to_index(self):
        response = self.client.get(
            reverse("admin_dashboard"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:index"))

    def test_manager_admin_login_public_chrome(self):
        response = Client().get("/authentication/login/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rmc-footer-surface=\"operator-compact\"")
        self.assertContains(response, "rmc-manager-login-footer")
        self.assertNotContains(response, "mkt-footer-command")
        self.assertContains(response, "Platform status")
        self.assertContains(response, "Find campus")
        self.assertContains(response, "rmc-footer-surfaces.css")

    def test_manager_portal_bridge_feature_control_compact_footer(self):
        """portal_base manager pages (e.g. Feature Control) use operator-compact footer."""
        url = reverse(
            "siteconfig:feature_control_panel",
            urlconf="config.manager_urls",
        )
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-rmc-footer-surface="operator-compact"')
        self.assertContains(response, "data-rmc-manager-operator-footer")
        self.assertContains(response, "rmc-manager-login-footer")
        self.assertContains(response, "manager-corporate-footer.css")
        self.assertNotContains(response, 'data-rmc-footer-surface="tenant-standard"')
        self.assertNotContains(response, "mkt-footer-command")

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
        response = self.client.get("/admin/", HTTP_HOST=self.host, follow=False)
        self.assertIn(
            response.status_code,
            (200, 302),
            msg=f"unexpected admin index status; Location={response.get('Location', '')}",
        )
        if response.status_code == 302:
            response = self.client.get(response["Location"], HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("cp-admin-index", html)
        self.assertIn("Platform Backoffice", html)
        self.assertIn('id="cp-main-content"', html)
        self.assertIn("admin-manager-shell", html)
        self.assertIn('data-rmc-control-plane-chrome="1"', html)
        self.assertIn("rmc-platform-chrome-layout.css", html)
        self.assertIn('data-rmc-cp-scroll="document"', html)
        self.assertIn("cp-admin-app-list", html)
        self.assertIn("Applications", html)
        self.assertIn("data-rmc-page-fold-nav", html)
        self.assertIn("rmc-page-fold-nav", html)
        self.assertIn("data-rmc-operator-surface-strip", html)

    def test_manager_super_and_admin_share_operator_topbar(self):
        super_resp = self.client.get("/super/", HTTP_HOST=self.host)
        admin_resp = self.client.get("/admin/", HTTP_HOST=self.host)
        self.assertEqual(super_resp.status_code, 200)
        self.assertEqual(admin_resp.status_code, 200)
        for marker in (
            'id="cpSearchInput"',
            "data-rmc-header-theme-chip",
            'data-shell-nav-bridge="manager-operator"',
        ):
            self.assertIn(marker, super_resp.content.decode())
            self.assertIn(marker, admin_resp.content.decode())

    def test_configuration_center_shows_surface_strip(self):
        response = self.client.get(
            reverse("configuration:center"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")

    def test_marketplace_workbench_shows_operator_surface_strip(self):
        path = reverse("super:marketplace_governance")
        ctx = build_operator_surface_ia_context(self._manager_super_request(path))
        self.assertTrue(ctx["RMC_OPERATOR_SURFACE_STRIP_VISIBLE"])
        self.assertEqual(ctx["RMC_OPERATOR_PAIRED_LINKS"], [])

    def test_marketplace_app_catalog_operational_frame_omits_admin_bridge(self):
        from apps.platform_runtime.operational_center_nav import (
            app_catalog_frame_context,
            enrich_operational_frame_context,
        )

        path = reverse("super:app_catalog")
        frame = enrich_operational_frame_context(
            self._manager_super_request(path),
            app_catalog_frame_context(),
        )
        self.assertFalse(frame.get("tertiary_url"))
        self.assertNotIn("Open platform admin", str(frame.get("tertiary_label", "")))

    def test_security_hub_omits_admin_bridge_chip(self):
        response = self.client.get(
            reverse("super:security_hub"), HTTP_HOST=self.host
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-operator-surface-strip")
        self.assertNotContains(response, "Open platform admin")
        self.assertNotContains(response, "Platform admin")

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
