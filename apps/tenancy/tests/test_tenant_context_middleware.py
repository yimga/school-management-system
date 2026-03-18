from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.tenancy.middleware import build_tenant_context_from_request


class TenantContextMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch(
        "apps.siteconfig.tenant_config.get_tenant_locale",
        return_value={"timezone": "Africa/Lagos"},
    )
    def test_rls_school_uses_live_school_json_fields(self, _mock_locale):
        school = SimpleNamespace(
            id="school-1",
            country="NG",
            features={"transport": True},
            settings={"grading_logic": "competency"},
        )
        request = self.factory.get("/", HTTP_HOST="tenant.example.com")
        request.school = school

        context = build_tenant_context_from_request(request)

        self.assertEqual(context.host, "tenant.example.com")
        self.assertEqual(context.feature_flags, {"transport": True})
        self.assertEqual(context.policy_overrides, {"grading_logic": "competency"})
        self.assertEqual(context.timezone, "Africa/Lagos")

    @patch(
        "apps.siteconfig.tenant_config.get_tenant_locale",
        return_value={"default_timezone": "Africa/Douala"},
    )
    def test_schema_tenant_falls_back_to_legacy_json_aliases(self, _mock_locale):
        school = SimpleNamespace(
            id="school-2",
            country="CM",
            features_json={"library": False},
            settings_json={"attendance_mode": "strict"},
        )
        tenant = SimpleNamespace(id="tenant-1", schema_name="tenant_one", school=school)
        request = self.factory.get("/", HTTP_HOST="tenant.example.com")
        request.tenant = tenant

        context = build_tenant_context_from_request(request)

        self.assertEqual(context.tenant_id, "tenant-1")
        self.assertEqual(context.schema_name, "tenant_one")
        self.assertEqual(context.feature_flags, {"library": False})
        self.assertEqual(context.policy_overrides, {"attendance_mode": "strict"})
        self.assertEqual(context.timezone, "Africa/Douala")
