"""API tests for product-tier engine room endpoints."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase
from apps.portal.views_ai_product import (
    api_guardrail_report_generator,
    api_guided_tour_planner,
    api_import_error_resolver,
    api_smart_settings_assistant,
)

class ProductAssistantApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = MagicMock()
        self.user.is_authenticated = True
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.pk = 1

    def _bare_view(self, view):
        fn = view
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        return fn

    def _post(self, view, path, payload):
        request = self.factory.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = self.user
        request.school = None
        return self._bare_view(view)(request)

    @patch("apps.portal.views_ai_product._gateway_rate_limit", return_value=None)
    @patch("apps.portal.views_ai_product._log_gateway_audit")
    @patch("apps.portal.views_ai_product.smart_settings_assist")
    def test_smart_settings_returns_response(self, mock_assist, _log, _rate):
        mock_assist.return_value = {
            "success": True,
            "response": "**Direct Answer**: Yes.",
            "escalation_required": False,
            "meta": {"tier": "rules"},
        }
        resp = self._post(
            api_smart_settings_assistant,
            "/api/ai/smart-settings/",
            {"query": "change school logo"},
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data["success"])
        self.assertIn("Direct Answer", data["response"])

    @patch("apps.portal.views_ai_product._gateway_rate_limit", return_value=None)
    @patch("apps.portal.views_ai_product._log_gateway_audit")
    @patch("apps.portal.views_ai_product.resolve_import_errors")
    def test_import_resolver_accepts_errors(self, mock_resolve, _log, _rate):
        mock_resolve.return_value = {
            "success": True,
            "guided": {"summary": "1 issue", "actions": [], "cautions": [], "references": []},
            "fixes": [],
            "meta": {},
        }
        resp = self._post(
            api_import_error_resolver,
            "/api/ai/import-error-resolver/",
            {"errors": [{"row": 1, "message": "required field missing"}]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)["success"])

    @patch("apps.portal.views_ai_product._gateway_rate_limit", return_value=None)
    @patch("apps.portal.views_ai_product._log_gateway_audit")
    @patch("apps.portal.views_ai_product.plan_guided_tour")
    def test_guided_tour_requires_goal(self, mock_plan, _log, _rate):
        mock_plan.return_value = {"success": True, "steps": [], "meta": {}}
        resp = self._post(
            api_guided_tour_planner,
            "/api/ai/guided-tour/",
            {"goal": "onboard teachers"},
        )
        self.assertEqual(resp.status_code, 200)

    @patch("apps.portal.views_ai_product._gateway_rate_limit", return_value=None)
    @patch("apps.portal.views_ai_product._log_gateway_audit")
    @patch("apps.portal.views_ai_product.guardrail_report_recommend")
    def test_guardrail_report_returns_recommendations(self, mock_report, _log, _rate):
        mock_report.return_value = {
            "success": True,
            "recommendations": [{"name": "Enrollment", "description": "Roster", "fit": "high"}],
            "meta": {},
            "guided": {"summary": "1 report", "actions": [], "cautions": [], "references": []},
        }
        resp = self._post(
            api_guardrail_report_generator,
            "/api/ai/guardrail-report/",
            {"query": "enrollment summary"},
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(len(data.get("recommendations") or []), 1)
