"""Edge sync chrome context processor — platform-wide progress bar wiring."""

from __future__ import annotations

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.context import edge_sync_chrome


@override_settings(RMC_EDGE_SYNC_ENABLED=True)
class EdgeSyncChromeContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Edge Chrome School",
            slug="edge-chrome",
            subdomain="edge-chrome",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="edge_chrome_admin",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def test_enabled_emits_status_urls(self):
        request = self.factory.get("/")
        request.user = self.user
        request.school = self.school
        ctx = edge_sync_chrome(request)["edge_sync_chrome"]
        self.assertTrue(ctx["enabled"])
        self.assertIn("sync-center/status/", ctx["status_url"])

    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_disabled_when_flag_off(self):
        request = self.factory.get("/")
        request.user = self.user
        request.school = self.school
        ctx = edge_sync_chrome(request)["edge_sync_chrome"]
        self.assertFalse(ctx["enabled"])
