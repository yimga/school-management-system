"""Optional offboarding polish: email notifications + dual approval."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import Permission
from apps.schools.models import School, SchoolMembership
from apps.schools.super_views_tenant_offboarding import api_school_offboarding_dual_approve
from apps.schools.tenant_offboarding import (
    record_dual_approval,
    record_primary_dual_approval,
    request_self_service_closure,
)
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*"],
    TENANT_PURGE_REQUIRE_DUAL_APPROVAL="1",
    TENANT_OFFBOARDING_EMAIL_ENABLED="1",
    TENANT_SELF_SERVICE_OFFBOARDING_ENABLED="1",
)
class TenantOffboardingOptionalTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Optional Offboard",
            slug="optional-offboard-school",
            subdomain="optional-offboard-school",
            is_active=True,
            default_region=self.region,
        )
        self.op1 = User.objects.create_superuser("op1", "op1@example.com", "x")
        self.op2 = User.objects.create_superuser("op2", "op2@example.com", "x")
        self.admin = User.objects.create_user("tenant_admin", password="x", email="admin@school.test")
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN", is_primary=True
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )
        self.admin.feature_permissions.add(manage_perm)
        self.factory = RequestFactory()

    @patch("apps.communication.notification_service.send_email", return_value=True)
    def test_self_service_closure_sends_email(self, mock_send):
        request_self_service_closure(
            self.school, actor=self.admin, acknowledge=True
        )
        self.assertGreaterEqual(mock_send.call_count, 1)

    def test_dual_approval_two_operator_flow(self):
        record_primary_dual_approval(self.school, actor=self.op1)
        record_dual_approval(self.school, actor=self.op2)
        off = (self.school.settings or {}).get("offboarding") or {}
        self.assertTrue(off.get("dual_approved"))

    def test_dual_approval_rejects_same_operator(self):
        record_primary_dual_approval(self.school, actor=self.op1)
        with self.assertRaises(ValueError):
            record_dual_approval(self.school, actor=self.op1)

    def test_dual_approve_api_primary(self):
        request = self.factory.post(
            f"/super/api/schools/{self.school.id}/offboarding/dual-approve/",
            data=json.dumps({"step": "primary"}),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.op1
        request.public_host_kind = "manager"
        response = api_school_offboarding_dual_approve(request, school_id=self.school.id)
        self.assertEqual(response.status_code, 200)
