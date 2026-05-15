from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User


_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR_HOST],
    ROOT_URLCONF="config.urls",
)
class ManagerOfflineSyncRouteTests(TestCase):
    def _login_verified_superuser(self, client: Client, username: str):
        user = User.objects.create_user(
            username=username,
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        TOTPDevice.objects.create(user=user, name="test-device", confirmed=True)
        client.login(username=username, password="x" * 8)
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def test_anonymous_manager_user_is_blocked_from_offline_sync_center(self):
        response = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False).get(
            "/offline/sync/"
        )
        self.assertIn(response.status_code, {302, 403})
        self.assertNotEqual(response.status_code, 404)

    def test_root_urlconf_fallback_for_anonymous_offline_sync_is_not_404(self):
        response = Client(raise_request_exception=False).get("/offline/sync/")
        self.assertIn(response.status_code, {302, 403})
        self.assertNotEqual(response.status_code, 404)

    def test_manager_offline_sync_route_returns_explanatory_center(self):
        client = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False)
        self._login_verified_superuser(client, "manager_offline_super")

        response = client.get("/offline/sync/")
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Offline Sync Center", body)
        self.assertIn("tenant-scoped", body)
        self.assertIn("tenant boundary", body)
        self.assertIn("Select a school", body)
        self.assertIn('data-rmc-os-center="offline_sync_center"', body)
        self.assertIn("data-rmc-premium-shell=", body)

    def test_root_urlconf_fallback_preserves_control_plane_only_rendering(self):
        client = Client(raise_request_exception=False)
        self._login_verified_superuser(client, "root_offline_super")

        response = client.get("/offline/sync/")
        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Offline Sync Center", body)
        self.assertIn("tenant-scoped", body)
