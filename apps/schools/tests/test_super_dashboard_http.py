"""HTTP tests for super dashboard Phase H + operator curated links (batch 33 #406 / #417)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.schools.tests.manager_client import bind_manager_session, mark_manager_mfa_verified
from apps.platform_runtime.models import PlatformOperatorSuperDashboardLink


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
)
class SuperDashboardHttpTests(TestCase):
    def setUp(self):
        self.password = "testpass123"
        self.user = User.objects.create_user(
            username="super_dashboard_h",
            password=self.password,
            is_staff=True,
            is_superuser=True,
        )
        self.host = "manager.runmycampus.com"
        self.client = Client(HTTP_HOST=self.host)
        TOTPDevice.objects.get_or_create(
            user=self.user,
            name="super-dashboard-http",
            defaults={"confirmed": True},
        )
        self.client.get("/authentication/login/", HTTP_HOST=self.host)
        self.client.force_login(self.user)
        bind_manager_session(self.client)
        mark_manager_mfa_verified(self.client)
        warmup = self.client.get(reverse("super:dashboard"), HTTP_HOST=self.host, follow=False)
        self.assertEqual(
            warmup.status_code,
            200,
            warmup.headers.get("Location", warmup.status_code),
        )
        cache.clear()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_dashboard_post_redirects_to_get_without_full_render(self):
        url = reverse("super:dashboard") + "?month=2026-05"
        response = self.client.post(url, HTTP_HOST=self.host, follow=False)
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertNotIn("/authentication/login/", location)
        self.assertIn("month=2026-05", location)

    def test_dashboard_phase_h_skip_link_targets_main(self):
        url = reverse("super:dashboard")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#super-dashboard-main"', body)
        self.assertIn('id="super-dashboard-main"', body)

    def test_dashboard_renders_operator_super_dashboard_curated_links(self):
        PlatformOperatorSuperDashboardLink.objects.create(
            slug="batch-33-cc",
            label="Open command center",
            href="/super/command-center/",
            sort_order=0,
        )
        url = reverse("super:dashboard")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open command center", body)
        self.assertIn('href="/super/command-center/"', body)
