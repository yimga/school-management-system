"""Phase H skip-link targets for Runtime inspector (batch 23 #256)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class RuntimeInspectorPhaseHTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="runtime_inspector_phase_h",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator page: bind the manager session with confirmed +
        # verified MFA (a bare force_login bounces 302). See login_manager_client.
        self.client = login_manager_client(self.user, password="testpass123")
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_runtime_inspector_phase_h_skip_link_targets_main(self):
        url = reverse("super:runtime_inspector")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#runtime-inspector-main"', body)
        self.assertIn('id="runtime-inspector-main"', body)
