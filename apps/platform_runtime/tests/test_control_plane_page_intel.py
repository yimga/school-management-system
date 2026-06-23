"""Page-aware "About this page" + "Your flow" on the control plane.

Pins the contract that the manager surfaces are page-specific, not one generic
blurb / one fixed action list for every page.
"""

from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase

from apps.platform_runtime.control_plane_page_intel import (
    MANAGER_PAGES,
    humanised_page_help,
    manager_flow_steps,
    resolve_manager_page,
)


class ManagerPageIntelTests(SimpleTestCase):
    def test_mapped_page_has_first_class_help(self):
        intel = resolve_manager_page("super:tenant_health")
        self.assertIsNotNone(intel)
        self.assertTrue(intel["title"])
        self.assertTrue(intel["body"])
        self.assertNotIn("Operator workspace", intel["body"])

    def test_unmapped_page_returns_none(self):
        self.assertIsNone(resolve_manager_page("super:does_not_exist_view"))

    def test_humanised_help_is_page_specific(self):
        out = humanised_page_help("super:tenant_directory_export", "super")
        self.assertIsNotNone(out)
        title, body = out
        self.assertEqual(title, "Tenant Directory Export")
        self.assertIn("operator control plane", body)

    def test_humanised_help_without_section_descriptor(self):
        title, body = humanised_page_help("widgets:nightly_recon", "widgets")
        self.assertEqual(title, "Nightly Recon")
        self.assertEqual(body, "Nightly Recon.")


class ManagerFlowAwarenessTests(SimpleTestCase):
    def test_flow_differs_per_page(self):
        # The whole point: two different pages must produce different onward flows.
        a = [s["viewname"] for s in manager_flow_steps("super:tenant_health", "super")]
        b = [s["viewname"] for s in manager_flow_steps("super:command_center", "super")]
        self.assertTrue(a and b)
        self.assertNotEqual(a, b)

    def test_flow_never_points_at_current_page(self):
        for view_name in MANAGER_PAGES:
            names = [s["viewname"] for s in manager_flow_steps(view_name, view_name.split(":", 1)[0])]
            self.assertNotIn(view_name, names, view_name)
            self.assertEqual(len(names), len(set(names)), f"{view_name} flow has dupes")

    def test_section_fallback_for_unmapped_super_page(self):
        steps = manager_flow_steps("super:some_unmapped_audit", "super")
        names = [s["viewname"] for s in steps]
        self.assertTrue(names)
        self.assertIn("super:tenant_health", names)

    def test_global_fallback_for_unknown_section(self):
        steps = manager_flow_steps("", "")
        self.assertTrue(steps)  # never an empty flow on the control plane

    def test_every_step_carries_title_and_body(self):
        for s in manager_flow_steps("super:dashboard", "super"):
            self.assertTrue(s["title"])
            self.assertTrue(s["body"])
            self.assertIsInstance(s["priority"], int)


class ControlPlaneActionsPageAwareTests(SimpleTestCase):
    """get_control_plane_actions reads the page-aware flow (URL-resolving)."""

    def _req(self, namespace, url_name, path):
        match = Mock()
        match.namespace = namespace
        match.url_name = url_name
        req = Mock()
        req.resolver_match = match
        req.path = path
        return req

    def _staff(self):
        return Mock(is_authenticated=True, is_staff=True, is_superuser=False)

    def test_actions_are_page_aware(self):
        from apps.platform_runtime.action_engine import get_control_plane_actions

        a = get_control_plane_actions(
            self._staff(), request=self._req("super", "tenant_health", "/super/tenant-health/")
        )
        b = get_control_plane_actions(
            self._staff(), request=self._req("super", "command_center", "/super/command-center/")
        )
        self.assertTrue(a, "mapped manager page must surface a flow")
        self.assertTrue(b)
        # page-aware: the onward titles are not identical between two pages
        self.assertNotEqual([x.title for x in a], [x.title for x in b])
        # never a dead URL
        self.assertTrue(all(x.action_url for x in a))

    def test_non_staff_gets_nothing(self):
        from apps.platform_runtime.action_engine import get_control_plane_actions

        anon = Mock(is_authenticated=True, is_staff=False, is_superuser=False)
        self.assertEqual(
            get_control_plane_actions(anon, request=self._req("super", "dashboard", "/super/")),
            [],
        )


class RouteHelpFallbackPageAwareTests(SimpleTestCase):
    def _req(self, namespace, url_name, host_kind="manager"):
        match = Mock()
        match.namespace = namespace
        match.url_name = url_name
        req = Mock()
        req.resolver_match = match
        req.public_host_kind = host_kind
        return req

    def test_unregistered_operator_page_is_humanised_not_generic(self):
        from apps.siteconfig.ui_route_help import resolve_route_help

        help = resolve_route_help(self._req("super", "totally_unregistered_audit_view"))
        self.assertEqual(help["title"], "Totally Unregistered Audit View")
        self.assertNotIn("Operator workspace", str(help["body"]))
        self.assertIn("operator control plane", str(help["body"]))
