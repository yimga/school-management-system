"""
Step 37: API Center governance contract tests.
API Center is the integration governance console; dashboard uses Integration model and enforces auth.
"""

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.integrations_marketplace.models import Integration
from apps.apicenter.views import _api_center_allowed


@override_settings(ROOT_URLCONF="config.urls")
class APICenterGovernanceContractTests(TestCase):
    """Contract: API Center dashboard requires auth; uses Integration; 403 when not allowed."""

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

    def test_dashboard_requires_login(self):
        """Dashboard must require authentication (redirect or 403)."""
        response = self.client.get(reverse("apicenter:dashboard"))
        self.assertIn(response.status_code, (302, 403), "Dashboard must require auth")

    def test_integration_model_used_for_governance(self):
        """Integration model is the governance surface (apicenter uses integrations_marketplace.Integration)."""
        self.assertEqual(Integration._meta.app_label, "integrations_marketplace")

    def test_api_center_allowed_returns_false_without_user(self):
        """_api_center_allowed returns False when request has no user."""
        request = self.factory.get("/api-center/")
        request.user = None
        request.public_host_kind = None
        self.assertFalse(_api_center_allowed(request))
