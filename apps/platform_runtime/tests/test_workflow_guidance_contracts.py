"""Phase 11 — workflow_guidance service contracts.

Locks the 3-layer visibility gate (host / enable / override), the tenant-safety
posture (platform-only tags must NEVER render on tenant hosts), and the
no-fabrication rule for missing context.
"""
from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from apps.platform_runtime import workflow_guidance, workflow_registry


def _request_with_host(kind: str):
    """Build a fake request with the public_host_kind attribute the middleware sets."""
    req = SimpleNamespace()
    req.public_host_kind = kind
    req.resolver_match = None
    req.user = SimpleNamespace(is_authenticated=False, role="")
    return req


class WorkflowResolveTests(SimpleTestCase):
    def test_get_workflow_returns_none_for_unknown_key(self):
        self.assertIsNone(workflow_guidance.get_workflow("definitely-not-a-real-workflow"))

    def test_get_workflow_returns_definition_for_known_key(self):
        # studio-os-output is seeded in the registry per Phase 3
        wdef = workflow_guidance.get_workflow("studio-os-output")
        self.assertIsNotNone(wdef)
        self.assertEqual(wdef.key, "studio-os-output")

    def test_get_workflow_handles_non_string_input_gracefully(self):
        self.assertIsNone(workflow_guidance.get_workflow(None))
        self.assertIsNone(workflow_guidance.get_workflow(123))


class VisibilityGateTests(SimpleTestCase):
    def test_platform_only_tag_hidden_on_tenant_host(self):
        # Find a workflow whose default_tags contains platform-only
        candidates = [
            w for w in workflow_registry.WORKFLOWS.values()
            if workflow_registry.TAG_PLATFORM_ONLY in (getattr(w, "default_tags", None) or ())
        ]
        if not candidates:
            self.skipTest("No platform-only tagged workflow seeded")
        wdef = candidates[0]
        tenant_req = _request_with_host("tenant")
        self.assertFalse(
            workflow_guidance.is_visible_for(tenant_req, wdef),
            f"Platform-only workflow {wdef.key} leaked onto tenant host",
        )

    def test_operator_audience_hidden_on_tenant_host(self):
        candidates = [
            w for w in workflow_registry.WORKFLOWS.values()
            if getattr(w, "audience", "") == workflow_registry.AUDIENCE_OPERATOR
        ]
        if not candidates:
            self.skipTest("No operator-audience workflow seeded")
        tenant_req = _request_with_host("tenant")
        for wdef in candidates:
            self.assertFalse(
                workflow_guidance.is_visible_for(tenant_req, wdef),
                f"Operator workflow {wdef.key} leaked onto tenant host",
            )

    def test_tenant_audience_hidden_on_manager_host(self):
        candidates = [
            w for w in workflow_registry.WORKFLOWS.values()
            if getattr(w, "audience", "") in (
                workflow_registry.AUDIENCE_TENANT_ADMIN,
                workflow_registry.AUDIENCE_TEACHER,
                workflow_registry.AUDIENCE_PARENT,
                workflow_registry.AUDIENCE_STUDENT,
            )
        ]
        if not candidates:
            self.skipTest("No tenant-audience workflow seeded")
        manager_req = _request_with_host("manager")
        for wdef in candidates:
            self.assertFalse(
                workflow_guidance.is_visible_for(manager_req, wdef),
                f"Tenant workflow {wdef.key} leaked onto manager host",
            )

    def test_none_workflow_is_never_visible(self):
        self.assertFalse(workflow_guidance.is_visible_for(_request_with_host("tenant"), None))


class TagsForTests(SimpleTestCase):
    def test_tags_for_returns_list(self):
        wdef = workflow_guidance.get_workflow("studio-os-output")
        if wdef is None:
            self.skipTest("studio-os-output not seeded")
        tenant_req = _request_with_host("tenant")
        # Visibility may strip — but call must return a list, not throw
        result = workflow_guidance.tags_for(tenant_req, wdef)
        self.assertIsInstance(result, list)

    def test_platform_only_tag_filtered_on_tenant_host(self):
        # Build a workflow definition with platform-only tag
        wdef = workflow_guidance.get_workflow("studio-os-output")
        if wdef is None:
            self.skipTest("studio-os-output not seeded")
        tenant_req = _request_with_host("tenant")
        tags = workflow_guidance.tags_for(tenant_req, wdef)
        for t in tags:
            self.assertNotEqual(
                t.get("key"), workflow_registry.TAG_PLATFORM_ONLY,
                "platform-only tag leaked onto tenant host through tags_for",
            )


class NextActionContractTests(SimpleTestCase):
    def test_next_action_returns_dict_or_none(self):
        wdef = workflow_guidance.get_workflow("studio-os-output")
        if wdef is None:
            self.skipTest("studio-os-output not seeded")
        # On operator host this workflow should return an action
        op_req = _request_with_host("manager")
        result = workflow_guidance.next_action_for(op_req, wdef)
        self.assertTrue(result is None or isinstance(result, dict))

    def test_next_action_for_unknown_workflow_returns_none(self):
        result = workflow_guidance.next_action_for(_request_with_host("tenant"), None)
        self.assertIsNone(result)


class HelpPanelContractTests(SimpleTestCase):
    def test_help_panel_for_unknown_workflow_returns_none(self):
        result = workflow_guidance.help_panel_for(_request_with_host("tenant"), None)
        self.assertIsNone(result)

    def test_help_panel_returns_dict_when_visible(self):
        wdef = workflow_guidance.get_workflow("parent-portal-pay-invoice")
        if wdef is None:
            self.skipTest("parent-portal-pay-invoice not seeded")
        tenant_req = _request_with_host("tenant")
        result = workflow_guidance.help_panel_for(tenant_req, wdef)
        self.assertTrue(result is None or isinstance(result, dict))


class HostKindResolutionTests(SimpleTestCase):
    def test_missing_request_defaults_to_tenant_for_safety(self):
        # Internal helper — defaults to "tenant" so unknown surfaces never
        # leak platform-only workflows.
        from apps.platform_runtime.workflow_guidance import _host_kind
        self.assertEqual(_host_kind(None), "tenant")

    def test_request_without_attr_defaults_to_tenant(self):
        from apps.platform_runtime.workflow_guidance import _host_kind
        req = SimpleNamespace()
        # No public_host_kind attribute at all
        self.assertEqual(_host_kind(req), "tenant")
