"""Tests for finance runtime_helpers.get_policy_for_request (runtime constitution)."""

from django.test import RequestFactory, TestCase

from apps.finance.runtime_helpers import get_policy_for_request


class GetPolicyForRequestTests(TestCase):
    def test_returns_empty_dict_when_no_request_attrs(self):
        request = RequestFactory().get("/")
        request.user = None
        result = get_policy_for_request(request)
        self.assertEqual(result, {})

    def test_uses_tenant_runtime_policy_when_set(self):
        request = RequestFactory().get("/")
        request.school = None
        request.tenant_runtime = type(
            "RT", (), {"policy": {"finance": {"invoice_timing": {"grace_days": 7}}}}
        )()

        result = get_policy_for_request(request)
        self.assertEqual(
            result.get("finance", {}).get("invoice_timing", {}).get("grace_days"), 7
        )

    def test_falls_back_to_policy_registry_when_no_runtime_but_school_set(self):
        from apps.schools.models import School

        school = School.objects.create(
            name="Test School Finance",
            slug="test-school-finance-runtime-helper",
            is_active=True,
        )
        request = RequestFactory().get("/")
        request.tenant_runtime = None
        request.school = school

        result = get_policy_for_request(request)
        self.assertIsInstance(result, dict)
        self.assertIn("finance", result)
