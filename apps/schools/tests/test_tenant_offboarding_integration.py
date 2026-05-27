"""Integration: URLs, nav wiring, schedule API, scheduled-purge command."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.schools.super_views_offboarding_queue import api_super_run_scheduled_purges
from apps.schools.super_views_offboarding_queue import api_school_offboarding_schedule
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"])
class TenantOffboardingIntegrationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="offboard_int",
            email="int@example.com",
            password="testpass123",
        )
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Integration Offboard",
            slug="integration-offboard-school",
            subdomain="integration-offboard-school",
            is_active=False,
            default_region=self.region,
        )

    def _manager_request(self, method: str, path: str, data: bytes | None = None):
        if method == "get":
            request = self.factory.get(path, HTTP_HOST="manager.runmycampus.com")
        else:
            request = self.factory.post(
                path,
                data=data or b"{}",
                content_type="application/json",
                HTTP_HOST="manager.runmycampus.com",
            )
        request.user = self.superuser
        request.public_host_kind = "manager"
        return request

    def test_super_url_names_resolve(self):
        specs = (
            ("offboarding_queue", []),
            ("api_run_scheduled_purges", []),
            ("api_school_offboarding", [self.school.id]),
            ("api_school_offboarding_schedule", [self.school.id]),
            ("api_school_offboarding_export_download", [self.school.id]),
        )
        for name, args in specs:
            with self.subTest(name=name):
                url = reverse(f"super:{name}", args=args)
                self.assertTrue(url.startswith("/"))

    def test_tenant_offboarding_urls_resolve(self):
        for name in (
            "tenant_offboarding",
            "tenant_offboarding_snapshot",
            "tenant_offboarding_request",
            "tenant_offboarding_cancel",
            "tenant_offboarding_export",
        ):
            with self.subTest(name=name):
                url = reverse(name, urlconf="config.tenant_urls")
                self.assertIn("offboarding", url)

    def test_operator_schedule_api(self):
        request = self._manager_request(
            "post",
            f"/super/api/schools/{self.school.id}/offboarding/schedule/",
            json.dumps({"scheduled_purge_at": "2099-06-01"}).encode(),
        )
        response = api_school_offboarding_schedule(request, school_id=self.school.id)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
        self.school.refresh_from_db()
        off = (self.school.settings or {}).get("offboarding") or {}
        self.assertEqual(off.get("scheduled_purge_at"), "2099-06-01")

    def test_run_scheduled_purges_api_dry_run(self):
        request = self._manager_request(
            "post",
            "/super/api/offboarding/run-scheduled/",
            json.dumps({"dry_run": True, "limit": 3}).encode(),
        )
        response = api_super_run_scheduled_purges(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))

    @override_settings(TENANT_AUTO_PURGE_ENABLED=False)
    def test_run_scheduled_purges_api_force_operator_confirm(self):
        request = self._manager_request(
            "post",
            "/super/api/offboarding/run-scheduled/",
            json.dumps(
                {
                    "dry_run": False,
                    "force_operator": True,
                    "confirm": "purge-due-tenants",
                    "limit": 1,
                }
            ).encode(),
        )
        response = api_super_run_scheduled_purges(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("force_operator"))

    @patch("apps.schools.tenant_offboarding.drop_tenant_schema_for_school", return_value=None)
    def test_scheduled_purge_management_command_dry_run(self, _mock):
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {
            "self_service_status": "scheduled",
            "scheduled_purge_at": "2000-01-01",
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        out = StringIO()
        call_command("tenant_offboarding_run_scheduled_purges", "--dry-run", stdout=out)
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())

    def test_control_plane_nav_includes_offboarding_queue(self):
        from apps.schools.control_plane_nav import build_control_plane_nav

        request = self._manager_request("get", "/super/offboarding/")
        groups = build_control_plane_nav(request)
        tenants = next(g for g in groups if g.get("label") == "Tenants")
        ids = [item["id"] for item in tenants.get("items") or []]
        self.assertIn("super_offboarding_queue", ids)

    def test_studio_hub_link_urls_include_offboarding(self):
        from apps.siteconfig.views_tenant_studio_hub import _studio_hub_link_urls

        urls = _studio_hub_link_urls()
        self.assertIn("offboarding", urls)
        self.assertIn("offboarding", urls["offboarding"])
