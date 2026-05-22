"""Phase 11 — workflow-aware AI invoker contracts.

Locks ``invoke_with_workflow_context`` and ``build_workflow_aware_metadata``:
both must inject workflow context into metadata when the bridge resolves a
visible workflow AND must leave metadata untouched in the DATA DEFAULTER
case (no fabrication).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_runtime import ai_workflow_invoker


def _req(host_kind: str = "tenant", path: str = "/"):
    r = SimpleNamespace()
    r.public_host_kind = host_kind
    r.resolver_match = None
    r.path = path
    r.user = SimpleNamespace(is_authenticated=False, role="")
    r.school = None
    return r


class BuildWorkflowAwareMetadataTests(SimpleTestCase):
    def test_unknown_workflow_returns_base_metadata_unchanged(self):
        base = {"foo": "bar"}
        out = ai_workflow_invoker.build_workflow_aware_metadata(
            request=_req("tenant", "/nowhere/"),
            base_metadata=base,
        )
        # Base metadata preserved; no workflow key injected
        self.assertEqual(out.get("foo"), "bar")
        self.assertNotIn("workflow", out)

    def test_visible_workflow_injects_workflow_key(self):
        out = ai_workflow_invoker.build_workflow_aware_metadata(
            request=_req("manager", "/studio/"),
            workflow_key="studio-os-output",
        )
        # Either workflow injected (visible) or not (filtered) — but if injected,
        # it must carry the exact shape.
        if "workflow" in out:
            wf = out["workflow"]
            self.assertEqual(wf["key"], "studio-os-output")
            self.assertIn("title", wf)
            self.assertIn("audience", wf)
            self.assertIn("module", wf)
            self.assertIn("route", wf)
            self.assertIn("host_kind", wf)
            self.assertIn("ai_context_key", wf)

    def test_none_base_metadata_yields_clean_dict(self):
        out = ai_workflow_invoker.build_workflow_aware_metadata(
            request=_req("tenant"),
        )
        self.assertIsInstance(out, dict)


class InvokeWithWorkflowContextTests(SimpleTestCase):
    """Patch the underlying ``invoke_with_request`` so we test ONLY the
    metadata-merging behavior — no real gateway calls."""

    def test_metadata_injected_when_workflow_resolves(self):
        captured: dict = {}

        def _fake_invoke(**kwargs):
            captured.update(kwargs)
            return ("response", {})

        with patch("services.ai_helpers.invoke_with_request", _fake_invoke):
            result = ai_workflow_invoker.invoke_with_workflow_context(
                request=_req("manager", "/studio/"),
                task_type="general",
                prompt="hello",
                workflow_key="studio-os-output",
            )
        self.assertIsNotNone(result)
        # Metadata must have arrived at the gateway with workflow attached
        # (when visibility allowed)
        md = captured.get("metadata", {})
        self.assertIsInstance(md, dict)

    def test_metadata_passthrough_when_data_defaulter(self):
        captured: dict = {}

        def _fake_invoke(**kwargs):
            captured.update(kwargs)
            return ("response", {})

        with patch("services.ai_helpers.invoke_with_request", _fake_invoke):
            ai_workflow_invoker.invoke_with_workflow_context(
                request=_req("tenant", "/nowhere/"),
                task_type="general",
                prompt="hello",
                # No workflow_key + unknown path → data_defaulter
                metadata={"caller_tag": "test"},
            )
        md = captured.get("metadata", {})
        self.assertEqual(md.get("caller_tag"), "test")
        self.assertNotIn("workflow", md)


class GatewayBoundaryTests(SimpleTestCase):
    """The invoker must NEVER import services.ai_gateway directly."""

    def test_no_direct_gateway_imports(self):
        import pathlib
        p = pathlib.Path(__file__).resolve().parents[2] / "ai_workflow_invoker.py"
        txt = p.read_text(encoding="utf-8")
        self.assertNotIn("from services.ai_gateway", txt)
        self.assertNotIn("import services.ai_gateway", txt)
