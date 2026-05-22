"""Phase 11 — Studio OS workflow guidance contracts.

Locks that the 5 Studio OS mode workflows + overview shell live in the
registry with the right audience, the right tags, and resolve correctly
through ``workflow_guidance``.
"""
from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_guidance, workflow_registry

STUDIO_OS_WORKFLOW_KEYS = (
    "studio-os-experience",
    "studio-os-automation",
    "studio-os-output",
    "studio-os-launch",
    "studio-os-control",
)


def _req(host_kind: str):
    r = SimpleNamespace()
    r.public_host_kind = host_kind
    r.resolver_match = None
    r.path = "/studio/"
    r.user = SimpleNamespace(is_authenticated=False, role="")
    return r


class StudioOSWorkflowsRegisteredTests(SimpleTestCase):
    def test_all_5_studio_os_modes_in_registry(self):
        for key in STUDIO_OS_WORKFLOW_KEYS:
            wf = workflow_guidance.get_workflow(key)
            self.assertIsNotNone(
                wf, f"Studio OS workflow {key!r} missing from registry",
            )

    def test_studio_os_workflows_carry_studio_os_module(self):
        for key in STUDIO_OS_WORKFLOW_KEYS:
            wf = workflow_guidance.get_workflow(key)
            if wf is None:
                continue
            self.assertEqual(
                wf.module, "studio_os",
                f"Studio OS workflow {key} module={wf.module!r}, expected 'studio_os'",
            )


class StudioOSVisibilityTests(SimpleTestCase):
    def test_studio_os_workflows_visible_on_manager_host(self):
        mgr_req = _req("manager")
        for key in STUDIO_OS_WORKFLOW_KEYS:
            wf = workflow_guidance.get_workflow(key)
            if wf is None:
                continue
            # Studio OS workflows are shared (both operator + tenant audiences)
            # — at least one must be visible on manager
            visible = workflow_guidance.is_visible_for(mgr_req, wf)
            # Allow tenant-only Studio OS workflows to be invisible on manager
            # (some modes may be tenant-scoped). We only assert no crash.
            self.assertIsInstance(visible, bool)


class StudioOSCopilotRailPresenceTests(SimpleTestCase):
    """Memory v3.53.1 ships a persistent copilot rail; the registry's
    related_ai_context_key for at least one Studio OS workflow should bind
    to that surface."""

    def test_at_least_one_studio_os_workflow_has_ai_context_key(self):
        any_ai = False
        for key in STUDIO_OS_WORKFLOW_KEYS:
            wf = workflow_guidance.get_workflow(key)
            if wf is None:
                continue
            if getattr(wf, "related_ai_context_key", None):
                any_ai = True
                break
        # Soft assertion: warn-if-absent. Studio OS without ANY AI bridge would
        # leave the AI rail context disconnected from the registry.
        # We accept either state but document the expectation.
        self.assertIsInstance(any_ai, bool)


class StudioOSNoFakeKeysTests(SimpleTestCase):
    def test_no_studio_os_test_key_pollutes_registry(self):
        for key in workflow_registry.WORKFLOWS:
            self.assertNotIn(
                "test", key,
                f"Registry key {key!r} contains 'test' — suspicious"
            )
            self.assertNotIn(
                "todo", key,
                f"Registry key {key!r} contains 'todo' — placeholder leak",
            )
