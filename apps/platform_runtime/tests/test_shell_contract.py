"""Tests for ``shell_contract`` resolver and context processor."""

import unittest

from django.test import RequestFactory

from apps.platform_runtime.context_processors import shell_contract_context
from apps.platform_runtime.shell_contract import (
    manager_header_hide_config_chip,
    resolve_shell_contract,
    resolve_shell_dataclass,
    vertical_workspace_policy,
)


class ShellContractResolverTests(unittest.TestCase):
    def test_admin_path(self):
        rf = RequestFactory()
        req = rf.get("/admin/foo/")
        req.public_host_kind = "school"
        c = resolve_shell_dataclass(req)
        self.assertEqual(c.route_family, "admin")
        self.assertEqual(c.layout_token, "admin")
        self.assertEqual(c.nav_family, "admin")
        self.assertEqual(c.personality_os, "sovereign")

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
        self.assertEqual(ctx["rmc_shell"]["personality_os"], "fluid")
        for key in (
            "layout_token",
            "nav_family",
            "host_kind",
            "main_region",
            "personality_os",
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
            "manager_header_hide_config_chip",
            "cp_header_mode",
            "layout_density",
            "vertical_workspace_policy",
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

    def test_manager_header_hides_config_on_studio_and_operations(self):
        self.assertTrue(manager_header_hide_config_chip("/studio/"))
        self.assertTrue(manager_header_hide_config_chip("/studio/experience/"))
        self.assertTrue(manager_header_hide_config_chip("/super/command-center/"))
        self.assertFalse(manager_header_hide_config_chip("/super/dashboard/"))
        self.assertFalse(manager_header_hide_config_chip("/siteconfig/console/domains/"))

    def test_manager_shell_context_config_chip_flag(self):
        rf = RequestFactory()
        req = rf.get("/studio/")
        req.public_host_kind = "manager"
        ctx = resolve_shell_contract(req)
        self.assertTrue(ctx["manager_header_hide_config_chip"])
        req2 = rf.get("/super/dashboard/")
        req2.public_host_kind = "manager"
        ctx2 = resolve_shell_contract(req2)
        self.assertFalse(ctx2["manager_header_hide_config_chip"])

    def test_manager_portal_wrap_markers(self):
        rf = RequestFactory()
        req = rf.get("/portal/inbox/")
        req.public_host_kind = "manager"
        ctx = shell_contract_context(req)
        self.assertEqual(ctx["rmc_shell"]["portal_wrap_authenticated_shell"], "manager-embedded")
        self.assertEqual(ctx["rmc_shell"]["authenticated_surface"], "manager-control-plane")
        self.assertEqual(ctx["rmc_shell"]["shell_data_studio_host"], "control-plane")
        self.assertEqual(ctx["rmc_shell"]["cp_header_mode"], "consolidated")
        self.assertEqual(ctx["rmc_shell"]["layout_density"]["header_height"], "48px")

    def test_vertical_workspace_policy_all_hosts(self):
        policy = vertical_workspace_policy()
        self.assertEqual(policy["version"], "1")
        self.assertEqual(policy["heavy_chrome_rule"], "landing-only")
        rf = RequestFactory()
        for host in ("manager", "school"):
            req = rf.get("/")
            req.public_host_kind = host
            ctx = resolve_shell_contract(req)
            self.assertEqual(ctx["vertical_workspace_policy"]["scope"], "all-authenticated-shells")
            self.assertEqual(ctx["vertical_workspace_policy"]["global_marquee_rule"], "landing-only")

