"""Studio OS Co-pilot Rail views contract (v3.53.1, 2026-05-21).

Asserts:
  - Both endpoints require authentication (LoginRequiredMixin)
  - Authenticated GET returns valid JSON with expected keys
  - Failure inside the service returns a graceful 200 with empty arrays
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.studio_os.views_copilot_rail import (
    CopilotRailContextView,
    CopilotRailInsightsRefreshView,
    CopilotRailSendView,
    _prepare_rail_invoke,
)


def _attach_school(request, school):
    request.school = school
    return request


class CopilotRailViewsAuthTests(TestCase):
    """Anonymous requests must NOT see rail data."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_context_view_redirects_anonymous(self):
        request = self.factory.get("/studio/copilot/rail/context/")
        request.user = SimpleNamespace(is_authenticated=False)
        _attach_school(request, None)
        response = CopilotRailContextView.as_view()(request)
        # LoginRequiredMixin redirects (302) for anonymous.
        self.assertIn(response.status_code, (302, 403))

    def test_insights_view_redirects_anonymous(self):
        request = self.factory.get("/studio/copilot/rail/insights/")
        request.user = SimpleNamespace(is_authenticated=False)
        _attach_school(request, None)
        response = CopilotRailInsightsRefreshView.as_view()(request)
        self.assertIn(response.status_code, (302, 403))


class CopilotRailViewsShapeTests(TestCase):
    """Authenticated GET returns the documented JSON envelope."""

    def setUp(self):
        self.factory = RequestFactory()
        User = get_user_model()
        # Lightweight user — staff so command-bar registry has something to return.
        self.user = User.objects.create_user(
            username="rail-test-user",
            email="rail@example.com",
            password="x",
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

    def _request(self, path, params=None):
        url = path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{qs}"
        request = self.factory.get(url)
        request.user = self.user
        _attach_school(request, None)
        return request

    def test_context_view_returns_three_top_level_keys(self):
        request = self._request("/studio/copilot/rail/context/", {"mode": "experience"})
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=None,
        ):
            response = CopilotRailContextView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode("utf-8"))
        self.assertIn("snapshot", body)
        self.assertIn("insights", body)
        self.assertIn("quick_actions", body)

    def test_context_view_caps_insight_count(self):
        request = self._request("/studio/copilot/rail/context/", {"mode": "experience", "n": "999"})
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=None,
        ):
            response = CopilotRailContextView.as_view()(request)
        body = json.loads(response.content.decode("utf-8"))
        # Hard cap at 6 in the view; rail UI only renders 3.
        self.assertLessEqual(len(body.get("insights", [])), 6)

    def test_insights_view_returns_insights_only(self):
        request = self._request("/studio/copilot/rail/insights/", {"mode": "control"})
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=None,
        ):
            response = CopilotRailInsightsRefreshView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode("utf-8"))
        self.assertIn("insights", body)
        # Posture marker also surfaced for the JS pill.
        self.assertIn("posture_mode", body)

    def test_context_view_handles_service_failure_gracefully(self):
        """Service explosion -> 200 with empty arrays, never 500."""
        request = self._request("/studio/copilot/rail/context/", {"mode": "experience"})
        with patch(
            "apps.studio_os.views_copilot_rail.build_rail_payload",
            side_effect=RuntimeError("boom"),
        ):
            response = CopilotRailContextView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode("utf-8"))
        self.assertEqual(body.get("insights"), [])
        self.assertEqual(body.get("quick_actions"), [])
        self.assertEqual(body.get("error"), "unavailable")

    def test_insights_view_handles_service_failure_gracefully(self):
        request = self._request("/studio/copilot/rail/insights/", {"mode": "experience"})
        with patch(
            "apps.studio_os.views_copilot_rail.build_context_snapshot",
            side_effect=RuntimeError("boom"),
        ):
            response = CopilotRailInsightsRefreshView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode("utf-8"))
        self.assertEqual(body.get("insights"), [])


class CopilotRailUrlResolutionTests(TestCase):
    def test_context_url_resolves(self):
        url = reverse("studio_os:copilot_rail_context")
        self.assertTrue(url.endswith("/copilot/rail/context/"))

    def test_insights_url_resolves(self):
        url = reverse("studio_os:copilot_rail_insights")
        self.assertTrue(url.endswith("/copilot/rail/insights/"))


class CopilotRailSendRbacTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        User = get_user_model()
        self.school = SimpleNamespace(pk=1, slug="demo")
        self.teacher = User.objects.create_user(
            username="rail-teacher",
            email="teacher@example.com",
            password="x",
        )
        self.teacher.role = "TEACHER"
        self.teacher.save(update_fields=["role"])
        self.parent = User.objects.create_user(
            username="rail-parent",
            email="parent@example.com",
            password="x",
        )
        self.parent.role = "PARENT"
        self.parent.save(update_fields=["role"])

    def test_teacher_allowed_general_question(self):
        request = self.factory.post(
            "/studio/copilot/rail/send/",
            data=json.dumps({"message": "How do I take attendance?"}),
            content_type="application/json",
        )
        request.user = self.teacher
        _attach_school(request, self.school)
        envelope = _prepare_rail_invoke(
            request,
            "How do I take attendance?",
            mode="operator",
            surface="studio_os_copilot_rail",
        )
        self.assertTrue(envelope.allowed, envelope.denial_reason)
        self.assertEqual(envelope.permissions.get("scope"), "teacher")

    def test_parent_denied_payroll_keyword(self):
        request = self.factory.post(
            "/studio/copilot/rail/send/",
            data=json.dumps({"message": "Show me staff payroll totals"}),
            content_type="application/json",
        )
        request.user = self.parent
        _attach_school(request, self.school)
        envelope = _prepare_rail_invoke(
            request,
            "Show me staff payroll totals",
            mode="operator",
            surface="studio_os_copilot_rail",
        )
        self.assertFalse(envelope.allowed)
        self.assertIn("payroll", envelope.denial_reason.lower())

    @patch("services.ai_helpers.invoke_with_request")
    def test_send_view_returns_403_on_rbac_deny(self, mock_invoke):
        request = self.factory.post(
            "/studio/copilot/rail/send/",
            data=json.dumps({"message": "List every student salary"}),
            content_type="application/json",
        )
        request.user = self.parent
        _attach_school(request, self.school)
        response = CopilotRailSendView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content.decode("utf-8"))
        self.assertEqual(body.get("error"), "permission_denied")
        mock_invoke.assert_not_called()


class CopilotRailSendGuidedReplyTests(SimpleTestCase):
    """Rail send must surface guided_assistant payloads as readable chat text."""

    def setUp(self):
        self.factory = RequestFactory()
        self.operator = SimpleNamespace(
            is_authenticated=True,
            is_staff=True,
            is_superuser=True,
            pk=1,
            role="ADMIN",
        )

    @patch("apps.studio_os.views_copilot_rail._prepare_rail_invoke")
    @patch("services.ai_helpers.invoke_with_request")
    def test_send_view_formats_guided_assistant_dict(self, mock_invoke, mock_prepare):
        from services.ai_copilot_rbac import CopilotRbacEnvelope

        mock_prepare.return_value = CopilotRbacEnvelope(
            allowed=True,
            denial_reason="",
            permissions={"scope": "admin"},
            prompt="test prompt",
            metadata={"surface": "studio_os_copilot_rail"},
        )
        mock_invoke.return_value = (
            {
                "summary": "Use Rapid Create to add a tenant.",
                "actions": [{"title": "Open Rapid Create", "detail": "/super/schools/rapid/"}],
                "cautions": [],
                "references": [],
            },
            {"provider": "rules", "tier": "rules", "posture_mode": "guided"},
        )
        request = self.factory.post(
            "/studio/copilot/rail/send/",
            data=json.dumps({"message": "how can i add a tenant"}),
            content_type="application/json",
        )
        request.user = self.operator
        request.public_host_kind = "manager"
        _attach_school(request, None)
        response = CopilotRailSendView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode("utf-8"))
        self.assertIn("Rapid Create", body.get("reply", ""))
        self.assertEqual(body.get("source"), "rules")
        mock_invoke.assert_called_once()
        _kwargs = mock_invoke.call_args.kwargs
        self.assertEqual(_kwargs.get("response_schema"), "guided_assistant")
