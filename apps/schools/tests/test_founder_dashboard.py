"""Founder dashboard markers and graceful missing audit files."""

from __future__ import annotations

import os
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools import super_views_founder_dashboard


@override_settings(ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"])
class FounderDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="founder_mark_t",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.env = mock.patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_superuser_sees_markers(self):
        url = reverse("super:founder_dashboard")
        r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
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
            r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("not available", body)
        self.assertIn("missing", body)
