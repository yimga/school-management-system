"""Tests for portal runtime_helpers.get_policy_for_request (runtime constitution)."""
from django.test import RequestFactory, TestCase

from apps.portal.runtime_helpers import get_policy_for_request


class GetPolicyForRequestTests(TestCase):
    def test_returns_empty_dict_when_no_request_attrs(self):
        request = RequestFactory().get("/")
        request.user = None
        result = get_policy_for_request(request)
        self.assertEqual(result, {})

    def test_uses_tenant_runtime_policy_when_set(self):
        request = RequestFactory().get("/")
        request.school = None
        request.tenant_runtime = type("RT", (), {"policy": {"terminology": {"student_label": "Learner"}}})()

        result = get_policy_for_request(request)
        self.assertEqual(result.get("terminology", {}).get("student_label"), "Learner")

    def test_falls_back_to_policy_registry_when_no_runtime_but_school_set(self):
        from apps.schools.models import School
        school = School.objects.create(
            name="Test School",
            slug="test-school-runtime-helper",
            is_active=True,
        )
        request = RequestFactory().get("/")
        request.tenant_runtime = None
        request.school = school

        result = get_policy_for_request(request)
        self.assertIsInstance(result, dict)
        self.assertIn("terminology", result)

        school.delete()
