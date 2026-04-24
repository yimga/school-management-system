"""Batch 948: SchoolConfigAPI (AllowAny) — rate limit + audit alignment with public_endpoint_audit.md §2."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.schools.api_views import SchoolConfigAPI

_FAKE_SCHOOL = SimpleNamespace(
    pk=uuid.uuid4(),
    name="Config API School",
    logo_url="",
    primary_color="#0d6efd",
    accent_color="#198754",
)


@override_settings(ALLOWED_HOSTS=["*"])
class SchoolConfigAPIHardeningTests(SimpleTestCase):
    """III.31 / §6.12: hardening slice for the host-resolved public config endpoint (apps/schools/api_views)."""

    def setUp(self):
        self.factory = APIRequestFactory()

    def _get_view(self, request):
        return SchoolConfigAPI.as_view()(request)

    @patch("apps.api.rate_limit.throttle_ip_request", return_value=(False, 33))
    def test_rate_limit_returns_429_with_retry_header(self, _mock_throttle):
        request = self.factory.get(
            "/api/config/",
            HTTP_HOST="tenant.example.com",
        )
        request.school = None
        request.user = AnonymousUser()
        response = self._get_view(request)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.get("Retry-After"), "33")

    @patch("apps.schools.api_views.get_effective_offline_runtime_settings")
    @patch("apps.policies.policy_registry.get_effective_policy")
    @patch("apps.schools.api_views.logger")
    def test_audit_logs_authenticated_false_for_anonymous(
        self, mock_log, mock_policy, mock_offline
    ):
        mock_offline.return_value = {"enable_offline_mode": False}
        mock_policy.return_value = {"features": {"x": True}}
        with patch("apps.api.rate_limit.throttle_ip_request", return_value=(True, 0)):
            request = self.factory.get("/api/config/", HTTP_HOST="tenant.example.com")
            request.school = _FAKE_SCHOOL
            request.user = AnonymousUser()
            self._get_view(request)
        mock_log.info.assert_called()
        self.assertEqual(mock_log.info.call_args[0][0], "school_config_api_request")
        extra = mock_log.info.call_args[1]["extra"]
        self.assertEqual(extra["host"], "tenant.example.com")
        self.assertEqual(extra["school_id"], _FAKE_SCHOOL.pk)
        self.assertIs(extra["authenticated"], False)

    @patch("apps.schools.api_views.get_effective_offline_runtime_settings")
    @patch("apps.policies.policy_registry.get_effective_policy")
    @patch("apps.schools.api_views.logger")
    def test_audit_logs_authenticated_true_when_user_authenticated(
        self, mock_log, mock_policy, mock_offline
    ):
        mock_offline.return_value = {"enable_offline_mode": False}
        mock_policy.return_value = {"features": {}}
        user = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            pk=1,
            username="u",
        )
        with patch("apps.api.rate_limit.throttle_ip_request", return_value=(True, 0)):
            request = self.factory.get("/api/config/", HTTP_HOST="tenant.example.com")
            request.school = _FAKE_SCHOOL
            request.user = user
            self._get_view(request)
        extra = mock_log.info.call_args[1]["extra"]
        self.assertIs(extra["authenticated"], True)
