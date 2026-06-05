"""v4.02.14 — page- and dashboard-aware Tools tray payload tests."""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock.tools_tray_page_context import (
    build_tools_tray_page_payload,
    resolve_dashboard_kind,
    resolve_group_plan,
    resolve_page_title,
)


class ResolveDashboardKindTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _req(self, path: str, *, view_name: str = ""):
        req = self.rf.get(path)
        if view_name:
            req.resolver_match = mock.Mock(view_name=view_name)
        return req

    def test_super_dashboard_view_is_landing(self):
        req = self._req("/super/dashboard/", view_name="super:dashboard")
        self.assertEqual(resolve_dashboard_kind(req), "landing")

    def test_super_task_path_is_workspace_or_task(self):
        req = self._req("/super/migration/health/")
        kind = resolve_dashboard_kind(req)
        self.assertIn(kind, {"workspace", "task"})

    def test_student_portal_path_is_landing(self):
        req = self._req("/portal/student-portal/grades/", view_name="portal:student_portal_grades")
        self.assertEqual(resolve_dashboard_kind(req), "landing")

    def test_finance_path_title(self):
        req = self._req("/finance/invoices/")
        self.assertEqual(resolve_page_title(req), "Finance")

    def test_workflow_title_not_used_as_page_title(self):
        req = self._req("/finance/cash-office-closure/")
        title = resolve_page_title(req, workflow_title="Close cash office")
        self.assertEqual(title, "Finance")

    def test_cp_archetype_decision_console_is_landing(self):
        req = self._req("/super/command-center/")
        req.cp_page_archetype = "decision-console"
        self.assertEqual(resolve_dashboard_kind(req), "landing")


class ResolveGroupPlanTests(SimpleTestCase):
    def test_operator_landing_emphasizes_workflow_and_operator(self):
        plan = resolve_group_plan(
            surface="manager",
            dashboard_kind="landing",
            workflow_key="",
            is_tenant=False,
        )
        self.assertIn("workflow", plan["emphasize_groups"])
        self.assertIn("operator", plan["emphasize_groups"])
        self.assertEqual(plan["hide_groups"], [])

    def test_operator_task_without_workflow_hides_workflow_group(self):
        plan = resolve_group_plan(
            surface="manager",
            dashboard_kind="task",
            workflow_key="",
            is_tenant=False,
        )
        self.assertIn("workflow", plan["hide_groups"])
        self.assertIn("page", plan["emphasize_groups"])

    def test_tenant_landing_emphasizes_workspace(self):
        plan = resolve_group_plan(
            surface="portal",
            dashboard_kind="landing",
            workflow_key="",
            is_tenant=True,
        )
        self.assertIn("workspace", plan["emphasize_groups"])


class BuildToolsTrayPagePayloadTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_anonymous_returns_empty(self):
        req = self.rf.get("/super/dashboard/")
        req.user = mock.Mock(is_authenticated=False)
        self.assertEqual(build_tools_tray_page_payload(req), {})

    def test_authed_manager_payload_shape(self):
        req = self.rf.get("/super/dashboard/")
        req.public_host_kind = "manager"
        req.user = mock.Mock(
            is_authenticated=True,
            is_superuser=True,
            is_staff=True,
        )
        req.resolver_match = mock.Mock(view_name="super:dashboard")
        payload = build_tools_tray_page_payload(req)
        for key in (
            "path",
            "view_name",
            "title",
            "archetype",
            "dashboard_kind",
            "surface",
            "role",
            "groups",
            "quick_actions",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["dashboard_kind"], "landing")
        self.assertEqual(payload["view_name"], "super:dashboard")
        self.assertIsInstance(payload["quick_actions"], list)
        self.assertIn("order", payload["groups"])

    def test_page_path_override_is_honored(self):
        req = self.rf.get("/super/dashboard/")
        req.public_host_kind = "manager"
        req.user = mock.Mock(is_authenticated=True, is_superuser=True)
        req.resolver_match = mock.Mock(view_name="super:dashboard")
        payload = build_tools_tray_page_payload(req, page_path="/finance/invoices/")
        self.assertEqual(payload["path"], "/finance/invoices/")

    def test_tenant_slug_path_prefix_is_normalized(self):
        req = self.rf.get("/t/demo-school/portal/parent/")
        req.public_host_kind = "tenant"
        req.user = mock.Mock(is_authenticated=True, is_superuser=False, active_role="PARENT")
        req.resolver_match = mock.Mock(view_name="portal:parent_dashboard")
        payload = build_tools_tray_page_payload(req)
        self.assertEqual(payload["path"], "/portal/parent/")
        self.assertEqual(payload["dashboard_kind"], "landing")
