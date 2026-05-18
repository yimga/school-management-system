"""Wave 2 — Studio embed minimal chrome (no nested portal/CP shells)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission
from apps.studio_os.embed_render import request_wants_studio_embed


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class StudioEmbedChromeTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="studio_embed_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        perm, _ = Permission.objects.get_or_create(
            code="settings.feature_control",
            defaults={"name": "Feature control"},
        )
        cls.user.feature_permissions.add(perm)
        perm2, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.user.feature_permissions.add(perm2)

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        self.client.login(username="studio_embed_op", password="x" * 8)

    def test_request_wants_studio_embed(self):
        class R:
            GET = {"embed": "1"}

        self.assertTrue(request_wants_studio_embed(R()))

    def test_feature_control_embed_minimal_document(self):
        url = (
            reverse("siteconfig:feature_control_panel", urlconf="config.manager_urls")
            + "?embed=1"
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:400])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-studio-embed="1"', body)
        self.assertNotIn('data-rmc-os-shell="control-plane"', body)
        self.assertNotIn("portal_sidebar", body)
        self.assertIn("feature-control-panel", body)

    def test_theme_colors_embed_minimal_document(self):
        url = (
            reverse("siteconfig:theme_colors", urlconf="config.manager_urls")
            + "?embed=1"
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:400])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-studio-embed="1"', body)
        self.assertNotIn('data-rmc-os-shell="control-plane"', body)
