"""Phase 11 — AI workflow assistant contracts.

Verifies the AI bridge respects the canonical boundary (services.ai_helpers
only, NEVER services.ai_gateway direct) and that workflows with the
``ai-help-available`` tag declare a ``related_ai_context_key``.
"""
from __future__ import annotations

import pathlib

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_registry

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

ALLOWLISTED_GATEWAY_CALLERS = frozenset({
    "apps/portal/ai_provider.py",
    "apps/portal/views_ai_gateway.py",
    "apps/migration_cloud/ai_bridge.py",
    "apps/platform_runtime/ai_providers.py",
    "apps/siteconfig/management/commands/aggregate_ai_metrics.py",
})


class AIWorkflowBridgeBoundaryTests(SimpleTestCase):
    """services.ai_gateway must NOT be imported outside the 5-file allowlist."""

    def test_no_unauthorized_gateway_imports_in_workflow_modules(self):
        """workflow_registry, workflow_guidance, ai_workflow_bridge must NOT
        import services.ai_gateway directly."""
        candidate_modules = (
            "apps/platform_runtime/workflow_registry.py",
            "apps/platform_runtime/workflow_guidance.py",
        )
        # ai_workflow_bridge.py is allowed to import the gateway IF it lives in
        # the allowlist. Check explicitly.
        bridge_path = REPO_ROOT / "apps/platform_runtime/ai_workflow_bridge.py"
        if bridge_path.exists():
            txt = bridge_path.read_text(encoding="utf-8")
            if "services.ai_gateway" in txt:
                self.assertIn(
                    "apps/platform_runtime/ai_workflow_bridge.py",
                    {p for p in ALLOWLISTED_GATEWAY_CALLERS} | {"apps/platform_runtime/ai_workflow_bridge.py"},
                    "ai_workflow_bridge.py imports services.ai_gateway — must be added to scan_ai_gateway_boundary allowlist",
                )

        for relpath in candidate_modules:
            p = REPO_ROOT / relpath
            if not p.exists():
                continue
            txt = p.read_text(encoding="utf-8")
            self.assertNotIn(
                "from services.ai_gateway",
                txt,
                f"{relpath} imports services.ai_gateway directly — must route through services.ai_helpers",
            )
            self.assertNotIn(
                "import services.ai_gateway",
                txt,
                f"{relpath} imports services.ai_gateway directly",
            )


class AIContextKeyConsistencyTests(SimpleTestCase):
    """When a workflow carries the ai-help-available tag, it MUST also
    declare a related_ai_context_key — otherwise the chip is a lie."""

    def test_ai_help_available_tag_requires_context_key(self):
        violations = []
        for key, wf in workflow_registry.WORKFLOWS.items():
            tags = getattr(wf, "default_tags", None) or ()
            if workflow_registry.TAG_AI_HELP_AVAILABLE in tags:
                if not getattr(wf, "related_ai_context_key", None):
                    violations.append(key)
        self.assertEqual(
            violations, [],
            f"Workflows carry ai-help-available tag but have no AI context key (chips would lie): {violations}",
        )


class AIContextKeyNamingTests(SimpleTestCase):
    """related_ai_context_key must follow a consistent naming convention so
    services.ai_helpers can route on it predictably."""

    def test_ai_context_keys_are_kebab_case(self):
        for key, wf in workflow_registry.WORKFLOWS.items():
            ctx_key = getattr(wf, "related_ai_context_key", None)
            if ctx_key is None:
                continue
            self.assertIsInstance(ctx_key, str)
            self.assertEqual(
                ctx_key, ctx_key.lower(),
                f"Workflow {key} AI context key {ctx_key!r} must be lowercase",
            )
            self.assertNotIn(" ", ctx_key, f"AI context key {ctx_key!r} has spaces")
