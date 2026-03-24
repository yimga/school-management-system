import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.api.government_views import GovernmentAggregatesAPI
from apps.api.permissions import RoleBasedPermission


class RoleBasedPermissionTests(SimpleTestCase):
    def test_has_permission_uses_role_manager_when_primary_role_missing(self):
        request = SimpleNamespace(
            user=SimpleNamespace(
                is_authenticated=True,
                role="",
                roles=SimpleNamespace(all=lambda: [SimpleNamespace(code="LEADERSHIP")]),
            )
        )
        view = SimpleNamespace(action="update")

        self.assertTrue(RoleBasedPermission().has_permission(request, view))

    def test_has_permission_handles_missing_role_manager(self):
        request = SimpleNamespace(
            user=SimpleNamespace(
                is_authenticated=True,
                role="",
                roles=[],
            )
        )
        view = SimpleNamespace(action="retrieve")

        self.assertFalse(RoleBasedPermission().has_permission(request, view))


class GovernmentAggregatesApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_government_aggregates_returns_defaults_when_model_lookup_fails(self):
        request = self.factory.get("/api/government/aggregates/")
        request.user = SimpleNamespace(
            is_authenticated=True, is_superuser=True, is_staff=True
        )
        request.school = None

        with patch("django.apps.apps.is_installed", return_value=True):
            with patch("django.apps.apps.get_model", side_effect=LookupError):
                response = GovernmentAggregatesAPI.as_view()(request)

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schools_count"], 0)
        self.assertEqual(payload["students_count"], 0)
        self.assertEqual(payload.get("schema_version"), "1.1")
        self.assertIn("teachers_count", payload)
        self.assertIn("guardian_links_count", payload)
