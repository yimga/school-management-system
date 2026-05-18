"""Wave 3 — unified Studio workspace layout markers on manager host."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class StudioWorkspaceLayoutTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="studio_workspace_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        self.client.login(username="studio_workspace_op", password="x" * 8)
        self.urlconf = "config.manager_urls"

    def _assert_workspace(self, url_name: str) -> None:
        url = reverse(url_name, urlconf=self.urlconf)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-studio-workspace="1"', body)
        self.assertIn("studio-workspace.css", body)
        self.assertIn("data-rmc-studio-workspace-main", body)

    def test_control_mode_workspace(self):
        self._assert_workspace("studio_os:control")

    def test_output_mode_workspace(self):
        self._assert_workspace("studio_os:output")

    def test_launch_mode_workspace(self):
        self._assert_workspace("studio_os:launch")
