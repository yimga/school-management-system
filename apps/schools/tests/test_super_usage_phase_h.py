"""Phase H skip link for API usage hub (batch 28 #331)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class SuperUsagePhaseHTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_usage_phase_h",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_super_usage_phase_h_skip_link_targets_main(self):
        url = reverse("super:usage")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#super-usage-main"', body)
        self.assertIn('id="super-usage-main"', body)
