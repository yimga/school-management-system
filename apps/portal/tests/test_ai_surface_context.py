"""Unified AI surface context (batch 1393)."""

from django.test import RequestFactory, SimpleTestCase

from apps.portal.ai_surface_context import (
    active_url_from_context,
    build_ai_surface_context,
    merge_surface_metadata,
)


class AISurfaceContextTests(SimpleTestCase):
    def test_build_includes_path_and_role(self):
        rf = RequestFactory()
        request = rf.get("/finance/dashboard/")
        request.user = type("U", (), {"is_authenticated": False, "role": ""})()
        request.school = None
        ctx = build_ai_surface_context(request)
        self.assertEqual(ctx["current_path"], "/finance/dashboard/")
        self.assertEqual(ctx["active_url"], "/finance/dashboard/")
        self.assertEqual(ctx["surface_intent"], "module_inline")

    def test_merge_surface_metadata(self):
        ctx = {"current_path": "/kb/", "role": "TEACHER", "school_id": 3}
        merged = merge_surface_metadata({"user_id": 1}, ctx)
        self.assertEqual(merged["current_path"], "/kb/")
        self.assertEqual(merged["role"], "TEACHER")
        self.assertEqual(merged["school_id"], 3)
        self.assertEqual(merged["user_id"], 1)

    def test_active_url_fallback(self):
        self.assertEqual(active_url_from_context(None, fallback="/x/"), "/x/")
