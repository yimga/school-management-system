from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User


_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR_HOST],
    ROOT_URLCONF="config.urls",
)
class ManagerOfflineSyncRouteTests(TestCase):
    def test_anonymous_manager_user_is_blocked_from_offline_sync_center(self):
        response = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False).get(
            "/offline/sync/"
        )
        self.assertIn(response.status_code, {302, 403})

    def test_manager_offline_sync_route_returns_explanatory_center(self):
        client = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False)
        User.objects.create_user(
            username="manager_offline_super",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        client.login(username="manager_offline_super", password="x" * 8)

        response = client.get("/offline/sync/")
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Offline Sync Center", body)
        self.assertIn("tenant-scoped", body)
        self.assertIn("tenant boundary", body)
        self.assertIn("Select a school", body)
        self.assertIn('data-rmc-os-center="offline_sync_center"', body)
        self.assertIn("data-rmc-premium-shell=", body)
