"""Unified AI gear 2 — intent router, lesson outline, guide, MCP (batch 1396)."""

from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.portal.ai_intent_router import resolve_surface_intent
from apps.portal.ai_surface_context import build_ai_surface_context
from services.ai.mcp_product_server import list_tools, mcp_enabled


class IntentRouterTests(SimpleTestCase):
    def test_education_teacher_path(self):
        self.assertEqual(
            resolve_surface_intent("/portal/education/teacher/", "TEACHER"),
            "education_teacher",
        )

    def test_playbook_onboarding_path(self):
        self.assertEqual(
            resolve_surface_intent("/siteconfig/onboarding/", "ADMIN"),
            "workflow_playbook",
        )

    def test_surface_context_includes_intent(self):
        rf = RequestFactory()
        request = rf.get("/portal/education/teacher/")
        request.user = type("U", (), {"is_authenticated": True, "role": "TEACHER"})()
        request.school = type("S", (), {"pk": 1})()
        ctx = build_ai_surface_context(request)
        self.assertEqual(ctx["surface_intent"], "education_teacher")
        self.assertIn("label", ctx.get("surface_intent_meta") or {})


class McpGear2Tests(SimpleTestCase):
    def test_tool_catalog_includes_gear2(self):
        names = {t["name"] for t in list_tools()}
        self.assertIn("lesson_plan_outline", names)
        self.assertIn("guide_surfaces", names)
        self.assertGreaterEqual(len(names), 6)

    def test_mcp_still_off_by_default(self):
        self.assertFalse(mcp_enabled())
