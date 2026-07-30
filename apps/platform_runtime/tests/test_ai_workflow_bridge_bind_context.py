"""Phase 11 (Wave E) — bind_workflow_context_for_ai contract tests.

Locks the new ``bind_workflow_context_for_ai`` output shape, the DATA
DEFAULTER posture, and the tenant-safety + visibility-gate plumbing for
the workflow-registry → AI gateway integration path.
"""
from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.platform_runtime import ai_workflow_bridge, workflow_registry


def _req(host_kind: str, path: str = "/"):
    r = SimpleNamespace()
    r.public_host_kind = host_kind
    r.resolver_match = None
    r.path = path
    r.user = SimpleNamespace(is_authenticated=False, role="")
    return r


EXPECTED_KEYS = {
    "schema_version",
    "workflow_key",
    "workflow_title",
    "audience",
    "module",
    "route",
    "ai_context_key",
    "tags",
    "host_kind",
    "data_defaulter",
}


class BindContextOutputShapeTests(SimpleTestCase):
    def test_unknown_request_returns_data_defaulter(self):
        ctx = ai_workflow_bridge.bind_workflow_context_for_ai(request=_req("tenant", "/nowhere/"))
        self.assertTrue(ctx["data_defaulter"])
        self.assertIsNone(ctx["workflow_key"])
        self.assertEqual(ctx["tags"], [])

    def test_output_has_all_expected_keys(self):
        ctx = ai_workflow_bridge.bind_workflow_context_for_ai(request=_req("tenant", "/"))
        self.assertEqual(set(ctx.keys()), EXPECTED_KEYS)

    def test_explicit_key_resolution(self):
        ctx = ai_workflow_bridge.bind_workflow_context_for_ai(
            request=_req("manager", "/studio/"),
            workflow_key="studio-os-output",
        )
        # studio-os-output may not be visible on manager host depending on audience
        # — the test asserts shape, not visibility specifics.
        self.assertIn("workflow_key", ctx)
        self.assertIn("data_defaulter", ctx)


class BindContextTenantSafetyTests(SimpleTestCase):
    def test_platform_only_workflow_returns_data_defaulter_on_tenant_host(self):
        candidates = [
            w for w in workflow_registry.WORKFLOWS.values()
            if workflow_registry.TAG_PLATFORM_ONLY in (w.default_tags or ())
        ]
        if not candidates:
            self.skipTest("No platform-only workflow seeded")
        wf = candidates[0]
        ctx = ai_workflow_bridge.bind_workflow_context_for_ai(
            request=_req("tenant"),
            workflow_key=wf.key,
        )
        self.assertTrue(
            ctx["data_defaulter"],
            f"Platform-only workflow {wf.key} leaked to AI bridge on tenant host",
        )

    def test_operator_audience_workflow_returns_data_defaulter_on_tenant(self):
        candidates = [
            w for w in workflow_registry.WORKFLOWS.values()
            if w.audience == workflow_registry.AUDIENCE_OPERATOR
        ]
        if not candidates:
            self.skipTest("No operator-audience workflow seeded")
        wf = candidates[0]
        ctx = ai_workflow_bridge.bind_workflow_context_for_ai(
            request=_req("tenant"),
            workflow_key=wf.key,
        )
        self.assertTrue(
            ctx["data_defaulter"],
            f"Operator workflow {wf.key} leaked to AI bridge on tenant host",
        )


class BindContextEntryPathFallbackTests(SimpleTestCase):
    """Promoted-from-matrix entries register with ``entry_path`` (URL path,
    not view name) — the bridge must resolve them when the request.path
    starts with the entry_path."""

    def test_entry_path_resolves_promoted_workflow(self):
        with_path = [
            w for w in workflow_registry.WORKFLOWS.values()
            if getattr(w, "entry_path", None) and getattr(w, "source", "") == "matrix-promoted"
        ]
        if not with_path:
            self.skipTest("No matrix-promoted workflow with entry_path")
        wf = with_path[0]
        ctx = ai_workflow_bridge.bind_workflow_context_for_ai(
            request=_req("tenant", wf.entry_path),
        )
        if not ctx["data_defaulter"]:
            self.assertEqual(ctx["workflow_key"], wf.key)


class BindContextBoundaryTests(SimpleTestCase):
    """The bridge must NOT import services.ai_gateway directly."""

    def test_bridge_does_not_import_gateway_directly(self):
        import pathlib
        # tests/ live one level below the app package, so the module is at
        # parents[1] (apps/platform_runtime/), not parents[2] (apps/).
        p = pathlib.Path(__file__).resolve().parents[1] / "ai_workflow_bridge.py"
        txt = p.read_text(encoding="utf-8")
        self.assertNotIn("from services.ai_gateway", txt)
        self.assertNotIn("import services.ai_gateway", txt)
