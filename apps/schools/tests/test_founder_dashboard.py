"""Founder dashboard markers and graceful missing audit files."""

from __future__ import annotations

import uuid
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools import super_views_founder_dashboard
from apps.schools.tests.manager_client import login_manager_control_plane

_MANAGER_HOST = "manager.runmycampus.com"
_PASSWORD = "x" * 8


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class FounderDashboardTests(TestCase):
    def setUp(self):
        self.username = f"founder_mark_{uuid.uuid4().hex[:8]}"
        self.user = User.objects.create_user(
            username=self.username,
            password=_PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=_MANAGER_HOST)
        login_manager_control_plane(
            self.client,
            self.user,
            password=_PASSWORD,
            host=_MANAGER_HOST,
        )
    def test_superuser_sees_markers(self):
        url = reverse("super:founder_dashboard")
        r = self.client.get(url, HTTP_HOST=_MANAGER_HOST)
        self.assertEqual(
            r.status_code,
            200,
            msg=f"redirect={r.get('Location', '')!r}",
        )
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-founder-dashboard=", body)
        self.assertIn("data-rmc-self-heal-status=", body)
        self.assertIn("data-rmc-northstar-score=", body)
        self.assertIn("data-rmc-post-surface-status=", body)
        self.assertIn("data-rmc-business-value=", body)
        self.assertIn("data-rmc-observability-ledger=", body)

    def test_dashboard_degrades_when_generated_json_missing(self):
        url = reverse("super:founder_dashboard")
        orig = super_views_founder_dashboard._load_json

        def _fake_load_json(path):
            if path.name in {
                "northstar_audit.json",
                "kill_test_report.json",
                "northstar_self_heal_report.json",
                "observability_ledger.json",
            }:
                return None
            return orig(path)

        with mock.patch.object(
            super_views_founder_dashboard,
            "_load_json",
            side_effect=_fake_load_json,
        ):
            r = self.client.get(url, HTTP_HOST=_MANAGER_HOST)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("not available", body)
        self.assertIn("missing", body)
