"""Wave 4 — inlined feature control panel in Studio Control mode."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class StudioControlInlineTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="studio_control_inline",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        self.client.login(username="studio_control_inline", password="x" * 8)

    def test_control_mode_inlines_feature_panel_without_duplicate_h1(self):
        url = reverse("studio_os:control", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-studio-inline-control="1"', body)
        self.assertIn("data-rmc-studio-inline-control-summary", body)
        # Full-page header chrome should not render inside Studio inline shell.
        self.assertNotIn("feature-control-header", body)
