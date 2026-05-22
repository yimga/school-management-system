"""Phase 11 — tenant-audience workflow contracts.

Locks: tenant-admin / teacher / parent / student workflows are visible on
tenant hosts and HIDDEN on the manager host. Operator chrome must not bleed
across the boundary.
"""
from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_guidance, workflow_registry

TENANT_AUDIENCES = (
    workflow_registry.AUDIENCE_TENANT_ADMIN,
    workflow_registry.AUDIENCE_TEACHER,
    workflow_registry.AUDIENCE_PARENT,
    workflow_registry.AUDIENCE_STUDENT,
)


def _req(host_kind: str):
    r = SimpleNamespace()
    r.public_host_kind = host_kind
    r.resolver_match = None
    r.path = "/"
    r.user = SimpleNamespace(is_authenticated=False, role="")
    return r


class TenantWorkflowsVisibleOnTenantHostTests(SimpleTestCase):
    """Tenant-audience workflows must be visible on the tenant host."""

    def test_tenant_workflows_visible_on_tenant_host(self):
        tenant_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience in TENANT_AUDIENCES
        ]
        self.assertGreater(len(tenant_wfs), 0, "Registry should seed at least one tenant workflow")
        tenant_req = _req("tenant")
        invisible = [
            w.key for w in tenant_wfs
            if not workflow_guidance.is_visible_for(tenant_req, w)
            # Exception: a tenant workflow tagged platform-only is rare but legal
            # (operator-only management of tenant state). Allow such cases to pass.
            and workflow_registry.TAG_PLATFORM_ONLY not in (w.default_tags or ())
        ]
        self.assertEqual(
            invisible, [],
            f"Tenant workflows invisible on tenant host: {invisible}",
        )


class TenantWorkflowsHiddenOnManagerTests(SimpleTestCase):
    """Tenant-audience workflows must NOT render on the manager host
    (operator surface is not the place to do parent-level actions)."""

    def test_tenant_workflows_hidden_on_manager_host(self):
        tenant_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience in TENANT_AUDIENCES
        ]
        if not tenant_wfs:
            self.skipTest("No tenant-audience workflows seeded")
        mgr_req = _req("manager")
        leaked = [
            w.key for w in tenant_wfs
            if workflow_guidance.is_visible_for(mgr_req, w)
        ]
        self.assertEqual(
            leaked, [],
            f"Tenant workflows leaked onto manager host: {leaked}",
        )


class TenantSafeTaggingTests(SimpleTestCase):
    """When a tenant workflow carries the ``tenant-safe`` tag, that chip must
    survive the tag-filter pipeline on a tenant host."""

    def test_tenant_safe_chip_survives_on_tenant_host(self):
        candidates = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience in TENANT_AUDIENCES
            and workflow_registry.TAG_TENANT_SAFE in (w.default_tags or ())
        ]
        if not candidates:
            self.skipTest("No tenant-safe-tagged tenant workflow seeded")
        tenant_req = _req("tenant")
        for w in candidates:
            tags = workflow_guidance.tags_for(tenant_req, w)
            keys = [t.get("key") for t in tags]
            self.assertIn(
                workflow_registry.TAG_TENANT_SAFE, keys,
                f"tenant-safe chip dropped on tenant host for {w.key}",
            )


class TenantHostKindFallbackTests(SimpleTestCase):
    """Unknown host kinds must default to ``tenant`` so platform-only workflows
    never silently leak when middleware fails to attach ``public_host_kind``."""

    def test_unknown_host_kind_treated_as_tenant(self):
        # Simulate a request that's missing the attribute entirely
        weird_req = SimpleNamespace()
        weird_req.resolver_match = None
        weird_req.path = "/"
        # No public_host_kind attribute at all
        operator_wfs = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience == workflow_registry.AUDIENCE_OPERATOR
        ]
        if not operator_wfs:
            self.skipTest("No operator-audience workflows seeded")
        # All operator workflows should be hidden when host_kind is unknown
        # (defaults to "tenant" for safety)
        for w in operator_wfs:
            self.assertFalse(
                workflow_guidance.is_visible_for(weird_req, w),
                f"Operator workflow {w.key} visible on unknown host kind (should default to tenant=hidden)",
            )
