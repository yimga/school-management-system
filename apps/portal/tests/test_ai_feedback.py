import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.compliance.models import AuditLog
from apps.portal.views_ai_gateway import api_ai_feedback


class AIFeedbackEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=1, role="ADMIN")

    @patch("apps.portal.views_ai_gateway.AuditLog.objects.create")
    @patch("apps.portal.views_ai_gateway.record_feedback")
    @patch("apps.portal.views_ai_gateway._check_rate_limit")
    def test_feedback_records_operator_review(
        self,
        mock_rate_limit,
        mock_record_feedback,
        mock_audit_create,
    ):
        mock_rate_limit.return_value = (True, 0)
        mock_record_feedback.return_value = {
            "task_type": "setup_recommend",
            "tier": "ollama",
            "cost_class": "self_hosted",
            "tenant_id": "11",
            "school_id": "11",
            "accepted": True,
            "manual_correction": False,
            "request_date": "2026-03-12",
            "request_id": "req-1",
        }

        request = self.factory.post(
            "/api/ai/feedback/",
            data=json.dumps(
                {
                    "feature": "setup_assistant",
                    "task_type": "setup_recommend",
                    "tier": "ollama",
                    "accepted": True,
                    "manual_correction": False,
                    "request_id": "req-1",
                    "request_date": "2026-03-12",
                }
            ),
            content_type="application/json",
        )
        request.user = self.user
        request.school = SimpleNamespace(id=11)
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "test-agent"

        raw_view = api_ai_feedback.__wrapped__.__wrapped__.__wrapped__
        response = raw_view(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["meta"]["cost_class"], "self_hosted")
        mock_record_feedback.assert_called_once()
        self.assertEqual(
            mock_audit_create.call_args.kwargs["action"], AuditLog.Action.APPROVE
        )
