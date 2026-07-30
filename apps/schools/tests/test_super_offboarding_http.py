"""HTTP smoke: offboarding queue + tenant 360 render without 500."""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig
from apps.test_utils.http_clients import login_manager_client

_MANAGER_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    SECURE_SSL_REDIRECT=False,
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
)
class SuperOffboardingHttpTests(TransactionTestCase):
    def setUp(self):
        self.password = "testpass123"
        self.user = User.objects.create_user(
            username=f"super_offboard_http_{uuid.uuid4().hex[:8]}",
            password=self.password,
            is_staff=True,
            is_superuser=True,
        )
        self.host = _MANAGER_HOST
        # Manager-host operator pages need a confirmed device + verified MFA on a
        # manager-bound session; a bare client.login() bounces 302 to MFA setup.
        self.client = login_manager_client(self.user, password=self.password)
        cache.clear()
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="HTTP Offboard School",
            slug="http-offboard-school",
            subdomain="http-offboard-school",
            is_active=True,
            default_region=self.region,
            settings={
                "offboarding": {
                    "self_service_status": "scheduled",
                    "scheduled_purge_at": "2099-01-15",
                }
            },
        )
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

    def test_offboarding_queue_renders_200(self):
        url = reverse("super:offboarding_queue")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(
            response.status_code,
            200,
            msg=f"redirect={response.get('Location', '')!r}",
        )
        body = response.content.decode("utf-8")
        self.assertIn("Offboarding queue", body)
        self.assertIn("http-offboard-school", body)
        self.assertIn("page-data-super_offboarding_queue-1", body)
        self.assertIn("schools__super_offboarding_queue-1.js", body)
        self.assertNotIn("<!doctype html><!doctype", body.lower())

    def test_tenant_360_offboarding_panel_renders(self):
        url = reverse("super:tenant_360", args=[self.school.id])
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(
            response.status_code,
            200,
            msg=f"redirect={response.get('Location', '')!r}",
        )
        body = response.content.decode("utf-8")
        self.assertIn('id="offboarding"', body)
        self.assertIn("data-rmc-offboarding-panel", body)
        self.assertIn("page-data-schools__tenant_offboarding-1", body)
        self.assertIn("schools__tenant_offboarding-1.js", body)
        self.assertIn("http-offboard-school", body)

    def test_offboarding_snapshot_api_returns_json(self):
        url = reverse("super:api_school_offboarding", args=[self.school.id])
        response = self.client.get(
            url,
            HTTP_HOST=self.host,
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("school_slug"), self.school.slug)

    def test_run_scheduled_purges_api_returns_json(self):
        url = reverse("super:api_run_scheduled_purges")
        response = self.client.post(
            url,
            data=json.dumps({"dry_run": True, "limit": 3}),
            content_type="application/json",
            HTTP_HOST=self.host,
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
