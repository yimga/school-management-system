"""
Manager host: tenant-primary Studio hubs must redirect; platform operators still reach Platform Studio.
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

_MANAGER_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", _MANAGER_HOST, "localhost", "127.0.0.1"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class ManagerStudioHubBoundaryTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="mgr_studio_super",
            email="msb@example.com",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.tenant_staff = User.objects.create_user(
            username="mgr_studio_staff",
            email="mst@example.com",
            password="pass12345",
            is_staff=True,
            is_superuser=False,
        )

    def test_studio_workflow_hub_on_manager_redirects_for_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/studio/hubs/workflow/",
            HTTP_HOST=_MANAGER_HOST,
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/super/", response.url or "")

    def test_studio_approvals_hub_on_manager_redirects(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/studio/hubs/approvals/",
            HTTP_HOST=_MANAGER_HOST,
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/super/", response.url or "")

    def test_authentication_backend_on_manager_redirects(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/authentication/backend/",
            HTTP_HOST=_MANAGER_HOST,
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/super/", response.url or "")

    def test_studio_import_hub_on_manager_redirects(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/studio/hubs/import/",
            HTTP_HOST=_MANAGER_HOST,
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/super/", response.url or "")

    def test_platform_studio_experience_on_manager_allowed_for_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("studio_os:experience"),
            HTTP_HOST=_MANAGER_HOST,
            follow=False,
        )
        self.assertEqual(response.status_code, 200)

    def test_tenant_staff_cannot_use_manager_studio_experience(self):
        """Manager host requires control-plane access (not generic is_staff)."""
        self.client.force_login(self.tenant_staff)
        response = self.client.get(
            reverse("studio_os:experience"),
            HTTP_HOST=_MANAGER_HOST,
            follow=False,
        )
        self.assertEqual(response.status_code, 403)
