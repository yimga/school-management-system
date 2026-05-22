"""Phase B/C unified AI assistant contracts (batch 1394–1395)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.portal.help_proactive_inline import module_inline_assistant_for_request
from apps.portal.workflow_playbook_ai import (
    build_offboarding_playbook_context,
    build_onboarding_playbook_context,
)
from services.ai.mcp_product_server import list_tools, mcp_enabled


class WorkflowPlaybookContextTests(SimpleTestCase):
    def test_onboarding_context_includes_steps(self):
        blob = build_onboarding_playbook_context(progress={"percent": 12})
        self.assertIn("PLAYBOOK", blob)
        self.assertIn("academic_year", blob)

    def test_offboarding_context_includes_export(self):
        blob = build_offboarding_playbook_context(self_service={"status": "active", "grace_days": 30})
        self.assertIn("export", blob.lower())


class ModuleInlineAssistantTests(SimpleTestCase):
    def test_teacher_attendance_path_qualifies(self):
        class R:
            path = "/teacher/attendance/"
            user = type("U", (), {"is_authenticated": True})()

        out = module_inline_assistant_for_request(R())
        self.assertTrue(out.get("show_module_inline_help_assistant"))


class McpScaffoldTests(SimpleTestCase):
    def test_list_tools_non_empty(self):
        self.assertGreaterEqual(len(list_tools()), 6)

    def test_mcp_disabled_by_default(self):
        self.assertFalse(mcp_enabled())
