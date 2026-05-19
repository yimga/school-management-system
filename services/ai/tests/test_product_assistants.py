"""Tests for product-tier assistants (import resolver, reports, tours)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.ai.product_assistants import (
    guardrail_report_recommend,
    plan_guided_tour,
    resolve_import_errors,
)


class ImportResolverTests(unittest.TestCase):
    @patch("services.ai.product_assistants.search_topology", return_value=[])
    def test_duplicate_message_gets_import_path(self, _search):
        user = SimpleNamespace(is_authenticated=True, role="ADMIN")
        out = resolve_import_errors(
            user,
            [{"row": 3, "field": "student_id", "message": "duplicate key value"}],
        )
        self.assertTrue(out["success"])
        self.assertEqual(len(out["fixes"]), 1)
        self.assertIn("duplicate", out["fixes"][0]["execution_path"].lower())


class ReportGuardrailTests(unittest.TestCase):
    def test_permission_denied_without_reports_view(self):
        user = MagicMock()
        user.has_feature_permission.return_value = False
        out = guardrail_report_recommend(user, "enrollment summary")
        self.assertTrue(out.get("permission_denied"))
        self.assertEqual(out["recommendations"], [])


class GuidedTourTests(unittest.TestCase):
    @patch("services.ai.gateway.process_platform_query")
    @patch("services.ai.product_assistants.search_topology")
    def test_tour_returns_steps(self, mock_search, mock_engine):
        mock_search.return_value = [
            {
                "label": "AI Center",
                "path_label": "**Platform > AI Center**",
                "url": "/ai-center/",
                "locked": False,
            }
        ]
        mock_engine.return_value = {
            "success": True,
            "response": "**Direct Answer**: Start in AI Center.\n",
            "escalation_required": False,
            "meta": {},
        }
        user = SimpleNamespace(
            is_authenticated=True,
            role="ADMIN",
            is_staff=False,
            is_superuser=False,
        )
        out = plan_guided_tour(user, "set up admissions")
        self.assertTrue(out["success"])
        self.assertGreaterEqual(len(out["steps"]), 1)
