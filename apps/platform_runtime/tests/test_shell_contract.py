"""Tests for ``shell_contract`` resolver and context processor."""

import unittest

from django.test import RequestFactory

from apps.platform_runtime.context_processors import shell_contract_context
from apps.platform_runtime.shell_contract import resolve_shell_dataclass


class ShellContractResolverTests(unittest.TestCase):
    def test_admin_path(self):
        rf = RequestFactory()
        req = rf.get("/admin/foo/")
        req.public_host_kind = "school"
        c = resolve_shell_dataclass(req)
        self.assertEqual(c.route_family, "admin")
        self.assertEqual(c.layout_token, "admin")
        self.assertEqual(c.nav_family, "admin")

    def test_manager_super_path(self):
        rf = RequestFactory()
        req = rf.get("/super/dashboard/")
        req.public_host_kind = "manager"
        c = resolve_shell_dataclass(req)
        self.assertEqual(c.route_family, "super")
        self.assertEqual(c.layout_token, "control-plane")

    def test_tenant_siteconfig_path(self):
        rf = RequestFactory()
        req = rf.get("/siteconfig/console/")
        req.public_host_kind = "school"
        c = resolve_shell_dataclass(req)
        self.assertEqual(c.route_family, "siteconfig")
        self.assertEqual(c.layout_token, "tenant-app")

    def test_context_processor_returns_rmc_shell(self):
        rf = RequestFactory()
        req = rf.get("/portal/inbox/")
        req.public_host_kind = "school"
        ctx = shell_contract_context(req)
        self.assertIn("rmc_shell", ctx)
        self.assertEqual(ctx["rmc_shell"]["route_family"], "portal")
        for key in (
            "layout_token",
            "nav_family",
            "host_kind",
            "main_region",
            "portal_wrap_authenticated_shell",
            "authenticated_surface",
            "cp_layout_authenticated_shell",
            "shell_data_studio_host",
            "control_plane_product_title",
            "portal_shell_root",
            "portal_default_document_title",
            "shell_sidebar_control_plane",
            "tenant_portal_breadcrumb_surface",
            "control_plane_breadcrumb_surface",
            "studio_os_sidebar_token",
        ):
            self.assertIn(key, ctx["rmc_shell"], f"rmc_shell must include {key!r} for shell inventory")
        self.assertEqual(ctx["rmc_shell"]["host_kind"], "school")
        self.assertEqual(ctx["rmc_shell"]["main_region"], "main")
        self.assertEqual(ctx["rmc_shell"]["portal_wrap_authenticated_shell"], "tenant-portal")
        self.assertEqual(ctx["rmc_shell"]["authenticated_surface"], "tenant-portal")
        self.assertEqual(ctx["rmc_shell"]["shell_data_studio_host"], "tenant")
        self.assertEqual(
            ctx["rmc_shell"]["control_plane_product_title"],
            "RunMyCampus Manager",
        )
        self.assertEqual(ctx["rmc_shell"]["portal_shell_root"], "portal")
        self.assertEqual(ctx["rmc_shell"]["portal_default_document_title"], "Portal")
        self.assertEqual(ctx["rmc_shell"]["shell_sidebar_control_plane"], "control-plane")
        self.assertEqual(ctx["rmc_shell"]["tenant_portal_breadcrumb_surface"], "tenant-portal")
        self.assertEqual(ctx["rmc_shell"]["control_plane_breadcrumb_surface"], "control-plane")
        self.assertEqual(ctx["rmc_shell"]["studio_os_sidebar_token"], "studio-rail")

    def test_manager_portal_wrap_markers(self):
        rf = RequestFactory()
        req = rf.get("/portal/inbox/")
        req.public_host_kind = "manager"
        ctx = shell_contract_context(req)
        self.assertEqual(ctx["rmc_shell"]["portal_wrap_authenticated_shell"], "manager-embedded")
        self.assertEqual(ctx["rmc_shell"]["authenticated_surface"], "manager-control-plane")
        self.assertEqual(ctx["rmc_shell"]["shell_data_studio_host"], "control-plane")

