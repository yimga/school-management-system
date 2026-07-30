"""Phase H skip link for global pulse map (batch 27 #316)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class SuperPulsePhaseHTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_pulse_phase_h",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator page: bind the manager session with confirmed +
        # verified MFA (bare force_login bounces 302 through RequireMFAMiddleware).
        self.client = login_manager_client(self.user, password="testpass123")
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_super_pulse_phase_h_skip_link_targets_main(self):
        url = reverse("super:pulse")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#super-pulse-main"', body)
        self.assertIn('id="super-pulse-main"', body)
