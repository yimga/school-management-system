"""RBAC coverage for portal AI streaming endpoint."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from django.test import RequestFactory

from apps.portal.views_ai_stream import ai_stream_view


class AiStreamRbacTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("services.ai_deployment_posture.is_litellm_configured", return_value=True)
    @patch("services.ai_copilot_rbac.prepare_copilot_invoke")
    def test_denied_query_returns_sse_refusal(self, mock_prepare, _litellm):
        from services.ai_copilot_rbac import CopilotRbacEnvelope

        mock_prepare.return_value = CopilotRbacEnvelope(
            allowed=False,
            denial_reason="You don't have permission to access payroll data.",
            permissions={"scope": "teacher"},
            prompt="",
            metadata={},
        )
        request = self.factory.post(
            "/portal/ai/stream/",
            data=json.dumps({"prompt": "Show staff payroll totals"}),
            content_type="application/json",
        )
        request.user = SimpleNamespace(is_authenticated=True)
        request.public_host_kind = "tenant"
        request.school = object()
        request._dont_enforce_csrf_checks = True

        response = ai_stream_view(request)
        body = b"".join(response.streaming_content)
        self.assertIn(b"payroll", body.lower())
        self.assertIn(b"[DONE]", body)

    @patch("services.ai_deployment_posture.is_litellm_configured", return_value=True)
    @patch("services.ai_helpers.invoke_with_request_stream", return_value=None)
    @patch("services.ai_copilot_rbac.prepare_copilot_invoke")
    def test_allowed_query_uses_envelope_prompt(self, mock_prepare, mock_stream, _litellm):
        from services.ai_copilot_rbac import CopilotRbacEnvelope

        mock_prepare.return_value = CopilotRbacEnvelope(
            allowed=True,
            denial_reason="",
            permissions={"scope": "teacher"},
            prompt="[RBAC ENFORCEMENT — NON-NEGOTIABLE]\n\nUser question",
            metadata={"copilot_rbac_enforced": True},
        )
        request = self.factory.post(
            "/portal/ai/stream/",
            data=json.dumps({"prompt": "How do I take attendance?"}),
            content_type="application/json",
        )
        request.user = SimpleNamespace(is_authenticated=True)
        request.public_host_kind = "tenant"
        request.school = object()
        request._dont_enforce_csrf_checks = True

        response = ai_stream_view(request)
        list(response.streaming_content)
        mock_stream.assert_called_once()
        _kwargs = mock_stream.call_args.kwargs
        self.assertIn("RBAC ENFORCEMENT", _kwargs["prompt"])
        self.assertTrue(_kwargs["metadata"].get("copilot_rbac_enforced"))
