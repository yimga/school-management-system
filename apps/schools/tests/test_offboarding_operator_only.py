"""Operator-only offboarding: tenant request → operator approve → purge gates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.models import School
from apps.schools.super_views_tenant_offboarding import (
    api_school_offboarding_approve_request,
    api_school_offboarding_reject_request,
)
from apps.schools.tenant_offboarding import (
    apply_purge,
    approve_offboarding_request,
    dry_run_purge,
    get_self_service_snapshot,
    request_tenant_offboarding,
)
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*"],
    TENANT_SELF_SERVICE_OFFBOARDING_ENABLED="0",
    TENANT_AUTO_PURGE_ENABLED=False,
)
class OperatorOnlyOffboardingTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Operator Only School",
            slug="operator-only-school",
            subdomain="operator-only-school",
            is_active=True,
            is_approved=True,
            default_region=self.region,
        )
        self.tenant_admin = User.objects.create_user(
            username="tenant_admin_oo",
            email="admin@oo.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_superuser(
            username="oo_operator",
            email="op@example.com",
            password="testpass123",
        )

    def test_tenant_request_does_not_schedule_purge(self):
        with patch(
            "apps.schools.tenant_offboarding.run_wind_down_export",
            return_value=type("R", (), {"export_zip_path": "/tmp/x.zip"})(),
        ):
            result = request_tenant_offboarding(
                self.school,
                actor=self.tenant_admin,
                acknowledge=True,
            )
        self.assertEqual(result.get("mode"), "operator_request")
        snap = get_self_service_snapshot(self.school)
        self.assertEqual(snap["status"], "requested")
        self.assertIsNone(snap["scheduled_purge_at"])
        self.assertTrue(snap["operator_only"])
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_active)

    def test_purge_blocked_without_operator_approval(self):
        request_tenant_offboarding(
            self.school, actor=self.tenant_admin, acknowledge=True
        )
        preview = dry_run_purge(self.school, confirm_slug=self.school.slug)
        self.assertIn("operator_approval_required", preview.purge_blocked_reasons)

    @patch("apps.schools.tenant_offboarding.drop_tenant_schema_for_school", return_value=None)
    def test_approve_then_purge_allowed(self, _mock_drop):
        request_tenant_offboarding(
            self.school, actor=self.tenant_admin, acknowledge=True
        )
        approve_offboarding_request(self.school, actor=self.operator)
        preview = dry_run_purge(self.school, confirm_slug=self.school.slug)
        self.assertNotIn("operator_approval_required", preview.purge_blocked_reasons)

    @patch("apps.schools.tenant_offboarding.drop_tenant_schema_for_school", return_value=None)
    def test_apply_purge_requires_operator_approval_by_default(self, _mock_drop):
        school = School.objects.create(
            name="Purge Gate",
            slug="purge-gate-school",
            subdomain="purge-gate-school",
            is_active=False,
            default_region=self.region,
        )
        settings = dict(school.settings or {})
        settings["offboarding"] = {
            "operator_approved_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
        receipt = apply_purge(
            school,
            actor=self.operator,
            confirm_slug=school.slug,
            dry_run=False,
        )
        self.assertEqual(receipt.school_slug, "purge-gate-school")

    def test_approve_api(self):
        request_tenant_offboarding(
            self.school, actor=self.tenant_admin, acknowledge=True
        )
        request = self.factory.post(
            f"/super/api/schools/{self.school.id}/offboarding/approve-request/",
            data=b"{}",
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.operator
        request.public_host_kind = "manager"
        response = api_school_offboarding_approve_request(
            request, school_id=self.school.id
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
        self.school.refresh_from_db()
        snap = get_self_service_snapshot(self.school)
        self.assertEqual(snap["status"], "scheduled")
        self.assertTrue(snap.get("operator_approved_at"))

    def test_reject_api(self):
        request_tenant_offboarding(
            self.school, actor=self.tenant_admin, acknowledge=True
        )
        request = self.factory.post(
            f"/super/api/schools/{self.school.id}/offboarding/reject-request/",
            data=json.dumps({"reason": "retained"}).encode(),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.operator
        request.public_host_kind = "manager"
        response = api_school_offboarding_reject_request(
            request, school_id=self.school.id
        )
        self.assertEqual(response.status_code, 200)
        self.school.refresh_from_db()
        snap = get_self_service_snapshot(self.school)
        self.assertEqual(snap["status"], "rejected")
