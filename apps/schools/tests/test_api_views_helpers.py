from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.schools.api_views import _offline_enabled_for_request


class SchoolApiViewHelperTests(SimpleTestCase):
    def test_offline_enabled_returns_false_when_policy_lookup_fails(self):
        request = RequestFactory().get("/api/config")
        request.school = SimpleNamespace(id=1)
        request.user = None

        with (
            patch(
                "apps.schools.api_views.get_effective_offline_runtime_settings",
                return_value={"enable_offline_mode": True},
            ),
            patch(
                "apps.policies.policy_registry.get_effective_policy",
                side_effect=RuntimeError("policy unavailable"),
            ),
        ):
            self.assertFalse(_offline_enabled_for_request(request))

    def test_offline_enabled_uses_policy_flag_when_present(self):
        request = RequestFactory().get("/api/config")
        request.school = SimpleNamespace(id=1)
        request.user = None

        with (
            patch(
                "apps.schools.api_views.get_effective_offline_runtime_settings",
                return_value={"enable_offline_mode": True},
            ),
            patch(
                "apps.policies.policy_registry.get_effective_policy",
                return_value={"enabled": True},
            ),
        ):
            self.assertTrue(_offline_enabled_for_request(request))
