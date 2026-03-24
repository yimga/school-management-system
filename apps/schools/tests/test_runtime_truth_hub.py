"""Runtime truth hub: super-only read-only RuntimeDefaults + slim SiteSettings summary."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class RuntimeTruthHubTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="truth_hub_tester",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_runtime_truth_hub_renders_200(self):
        url = reverse("super:runtime_truth_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Runtime truth hub", html=False)
