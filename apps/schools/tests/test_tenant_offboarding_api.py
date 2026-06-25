"""Tenant offboarding API and service tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from apps.schools.models import School, SchoolProvisioningEvent
from apps.schools.super_views_tenant_offboarding import (
    api_school_offboarding,
    api_school_offboarding_export,
    api_school_offboarding_purge,
)
from apps.schools.tenant_offboarding import apply_purge, dry_run_purge
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"])
class TenantOffboardingApiTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="offboard_super",
            email="offboard@example.com",
            password="testpass123",
        )
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Offboard Test",
            slug="offboard-test-school",
            subdomain="offboard-test-school",
            is_active=True,
            is_approved=True,
            default_region=self.region,
        )

    def _request(self, method: str, path: str, data: bytes | None = None):
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

    def test_offboarding_snapshot_get(self):
        request = self._request(
            "get",
            f"/super/api/schools/{self.school.id}/offboarding/",
        )
        response = api_school_offboarding(request, school_id=self.school.id)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("school_slug"), self.school.slug)

    def test_purge_dry_run_requires_matching_slug(self):
        request = self._request(
            "post",
            f"/super/api/schools/{self.school.id}/offboarding/purge/",
            json.dumps({"confirm_slug": "wrong-slug", "dry_run": True}).encode(),
        )
        response = api_school_offboarding_purge(request, school_id=self.school.id)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        preview = body.get("preview", {})
        self.assertIn("confirm_slug_mismatch", preview.get("purge_blocked_reasons", []))

    def test_purge_dry_run_json(self):
        request = self._request(
            "post",
            f"/super/api/schools/{self.school.id}/offboarding/purge/",
            json.dumps(
                {"confirm_slug": self.school.slug, "dry_run": True}
            ).encode(),
        )
        response = api_school_offboarding_purge(request, school_id=self.school.id)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("dry_run"))
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())

    @patch("apps.lifecycle.purge_operations.mark_purge_phase")
    @patch("apps.schools.tenant_offboarding.drop_tenant_schema_for_school", return_value=None)
    def test_apply_purge_deletes_school(self, _mock_drop, _mock_phase):
        school = School.objects.create(
            name="Purge Me",
            slug="purge-me-school",
            subdomain="purge-me-school",
            is_active=False,
            default_region=self.region,
        )
        from datetime import datetime, timezone

        settings = dict(school.settings or {})
        settings["offboarding"] = {
            "operator_approved_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
        receipt = apply_purge(
            school,
            actor=self.superuser,
            confirm_slug=school.slug,
            dry_run=False,
        )
        self.assertFalse(School.objects.filter(slug="purge-me-school").exists())
        self.assertEqual(receipt.school_slug, "purge-me-school")

    def test_export_creates_provisioning_event(self):
        request = self._request(
            "post",
            f"/super/api/schools/{self.school.id}/offboarding/export/",
            json.dumps({"full": True}).encode(),
        )
        response = api_school_offboarding_export(request, school_id=self.school.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=self.school,
                event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_EXPORT,
            ).exists()
        )

    def test_legal_hold_blocks_purge(self):
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {"legal_hold_until": "2099-12-31"}
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        preview = dry_run_purge(self.school, confirm_slug=self.school.slug)
        self.assertIn("legal_hold_active", preview.purge_blocked_reasons)
