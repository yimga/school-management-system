"""Command bar — topology search + permission locks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.ai.command_bar import search_command_bar
from services.ai.topology_map import build_system_topology_map, search_topology, user_can_access_entry


class TopologyPermissionTests(SimpleTestCase):
    def test_teacher_blocked_from_staff_route(self):
        user = SimpleNamespace(role="TEACHER", is_staff=False, is_superuser=False, is_authenticated=True)
        entry = {"required_permissions": ["staff_required"]}
        allowed, missing = user_can_access_entry(user, entry)
        self.assertFalse(allowed)
        self.assertEqual(missing, "IS_STAFF")

    def test_system_topology_includes_ai_center(self):
        rows = build_system_topology_map(include_reflected=False)
        ids = {r.get("id") for r in rows}
        self.assertIn("ai_center", ids)
        self.assertIn("first_line_support", ids)

    def test_search_marks_gateway_console_locked_for_teacher(self):
        user = SimpleNamespace(role="TEACHER", is_staff=False, is_superuser=False, is_authenticated=True)
        rows = search_topology(user, "ai gateway", limit=20)
        gw = [r for r in rows if r.get("id") == "ai_gateway_console"]
        if gw:
            self.assertTrue(gw[0].get("locked"))


@override_settings(AI_GATEWAY_ENABLED=True, AI_ENGINE_ROOM_SUPPORT=True)
class CommandBarSearchTests(SimpleTestCase):
    @patch("services.ai.command_bar.process_platform_query")
    def test_search_skips_engine_when_include_ai_false(self, mock_engine):
        user = SimpleNamespace(role="ADMIN", is_staff=True, is_superuser=False, is_authenticated=True)
        out = search_command_bar(user, "help center", include_ai_snippet=False)
        self.assertIn("results", out)
        mock_engine.assert_not_called()

    @patch("services.ai.command_bar.process_platform_query")
    def test_search_can_add_documentation_snippet(self, mock_engine):
        user = SimpleNamespace(role="ADMIN", is_staff=True, is_superuser=False, is_authenticated=True)
        mock_engine.return_value = {
            "success": True,
            "response": "**Direct Answer**: Yes.\n**Execution Path**: **A > B**\n**Action Steps**:\n1. Go.\n",
            "escalation_required": False,
        }
        out = search_command_bar(user, "register teacher", include_ai_snippet=True)
        self.assertTrue(any(r.get("type") == "documentation" for r in out.get("results", [])))

    @patch("services.ai.command_bar.process_platform_query")
    def test_search_escalate_row_when_no_docs(self, mock_engine):
        user = SimpleNamespace(role="ADMIN", is_staff=True, is_superuser=False, is_authenticated=True)
        mock_engine.return_value = {
            "success": True,
            "response": "I cannot locate that workflow.",
            "escalation_required": True,
        }
        out = search_command_bar(user, "obscure workflow xyz", include_ai_snippet=True)
        self.assertTrue(out.get("escalation_required"))
        self.assertTrue(any(r.get("type") == "escalate" for r in out.get("results", [])))
