"""Phase 11 — operator-only workflow contracts.

Locks: every workflow with audience=operator OR with the platform-only tag
must be HIDDEN on tenant hosts. Catches tenant-data leakage at the
visibility-gate layer.
"""
from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_guidance, workflow_registry


def _req(host_kind: str):
    r = SimpleNamespace()
    r.public_host_kind = host_kind
    r.resolver_match = None
    r.path = "/"
    r.user = SimpleNamespace(is_authenticated=False, role="")
    return r


class OperatorAudienceHiddenOnTenantTests(SimpleTestCase):
    """Operator-audience workflows MUST be hidden on tenant hosts."""

    def test_all_operator_audience_workflows_hidden_on_tenant(self):
        operator_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience == workflow_registry.AUDIENCE_OPERATOR
        ]
        self.assertGreater(len(operator_wfs), 0, "Registry should seed at least one operator workflow")
        tenant_req = _req("tenant")
        leaked = [
            w.key for w in operator_wfs
            if workflow_guidance.is_visible_for(tenant_req, w)
        ]
        self.assertEqual(
            leaked, [],
            f"Operator-audience workflows leaked onto tenant host: {leaked}",
        )

    def test_platform_only_tagged_workflows_hidden_on_tenant(self):
        platform_only_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if workflow_registry.TAG_PLATFORM_ONLY in (w.default_tags or ())
        ]
        if not platform_only_wfs:
            self.skipTest("No platform-only-tagged workflows seeded")
        tenant_req = _req("tenant")
        leaked = [
            w.key for w in platform_only_wfs
            if workflow_guidance.is_visible_for(tenant_req, w)
        ]
        self.assertEqual(
            leaked, [],
            f"Platform-only tagged workflows leaked onto tenant host: {leaked}",
        )


class OperatorWorkflowsVisibleOnManagerTests(SimpleTestCase):
    """Operator-audience workflows MUST be visible on manager host."""

    def test_operator_workflows_visible_on_manager(self):
        operator_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience == workflow_registry.AUDIENCE_OPERATOR
        ]
        if not operator_wfs:
            self.skipTest("No operator-audience workflows seeded")
        mgr_req = _req("manager")
        invisible = [
            w.key for w in operator_wfs
            if not workflow_guidance.is_visible_for(mgr_req, w)
        ]
        self.assertEqual(
            invisible, [],
            f"Operator workflows invisible on manager host: {invisible}",
        )


class OperatorTagFilteringTests(SimpleTestCase):
    """``tags_for`` MUST strip the platform-only chip on tenant hosts even when
    the workflow itself is visible (e.g. shared workflows tagged platform-only
    for an operator-specific surface)."""

    def test_platform_only_chip_filtered_on_tenant_host(self):
        # Build a workflow with the platform-only tag and tenant-admin audience
        tenant_admin_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience == workflow_registry.AUDIENCE_TENANT_ADMIN
            and workflow_registry.TAG_PLATFORM_ONLY in (w.default_tags or ())
        ]
        if not tenant_admin_wfs:
            self.skipTest("No tenant-admin workflow with platform-only tag")
        tenant_req = _req("tenant")
        for w in tenant_admin_wfs:
            tags = workflow_guidance.tags_for(tenant_req, w)
            for t in tags:
                self.assertNotEqual(
                    t.get("key"), workflow_registry.TAG_PLATFORM_ONLY,
                    f"platform-only chip leaked on tenant host via {w.key}",
                )


class OperatorWorkflowRouteShapeTests(SimpleTestCase):
    """Operator workflows must declare a non-empty route (URL name or path)."""

    def test_all_operator_workflows_have_route_or_entry_path(self):
        operator_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience == workflow_registry.AUDIENCE_OPERATOR
        ]
        missing = [
            w.key for w in operator_wfs
            if not w.route and not getattr(w, "entry_path", None)
        ]
        self.assertEqual(
            missing, [],
            f"Operator workflows missing both route and entry_path: {missing}",
        )
