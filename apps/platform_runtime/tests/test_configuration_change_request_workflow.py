from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.platform_runtime.configuration_change_requests import (
    apply_approved_change_request,
    approve_change_request,
    cancel_change_request,
    create_change_request,
    reject_change_request,
    schedule_change_request,
)
from apps.platform_runtime.models import ConfigurationChangeRequest, PackInstallation
from apps.platform_runtime.pack_apply import apply_pack
from apps.schools.models import School


class ConfigurationChangeRequestWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Governance School", slug="governance-school", subdomain="governance-school", is_active=True)
        self.tenant_admin = User.objects.create_user(username="tenant_governance", password="x" * 8, role=User.Role.ADMIN, is_staff=True)
        self.operator = User.objects.create_user(username="platform_governance", password="x" * 8, role=User.Role.SUPERADMIN, is_staff=True, is_superuser=True)

    def test_high_risk_pack_apply_requires_approval(self):
        result = apply_pack("network-operator", pack_type="dashboard_pack", school=self.school, actor=self.operator, confirmed=True, platform_operator=True)

        self.assertFalse(result["ok"])
        self.assertIn("approved change request", result["errors"][0])

    def test_tenant_cannot_approve_platform_request(self):
        row = create_change_request(
            ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_key="network-operator",
            target_type="dashboard_pack",
            school=self.school,
            actor=self.tenant_admin,
            platform_operator=False,
        )

        with self.assertRaises(PermissionError):
            approve_change_request(row, actor=self.tenant_admin)

    def test_rejected_cancelled_and_scheduled_paths(self):
        rejected = create_change_request(
            ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_key="network-operator",
            target_type="dashboard_pack",
            school=self.school,
            actor=self.operator,
            platform_operator=True,
            idempotency_key="reject-me",
        )
        reject_change_request(rejected, actor=self.operator, notes="No rollout.")
        self.assertEqual(apply_approved_change_request(rejected, actor=self.operator)["ok"], False)

        cancelled = create_change_request(
            ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_key="network-operator",
            target_type="dashboard_pack",
            school=self.school,
            actor=self.operator,
            platform_operator=True,
            idempotency_key="cancel-me",
        )
        approve_change_request(cancelled, actor=self.operator)
        cancel_change_request(cancelled, actor=self.operator)
        self.assertEqual(apply_approved_change_request(cancelled, actor=self.operator)["ok"], False)

        scheduled = create_change_request(
            ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_key="network-operator",
            target_type="dashboard_pack",
            school=self.school,
            actor=self.operator,
            platform_operator=True,
            idempotency_key="schedule-me",
        )
        approve_change_request(scheduled, actor=self.operator)
        schedule_change_request(scheduled, actor=self.operator, scheduled_at=timezone.now() + timedelta(days=1), execution_window="Friday 22:00")
        result = apply_approved_change_request(scheduled, actor=self.operator)
        self.assertFalse(result["ok"])
        self.assertTrue(result["scheduled"])

    def test_approved_request_can_apply(self):
        row = create_change_request(
            ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_key="network-operator",
            target_type="dashboard_pack",
            school=self.school,
            actor=self.operator,
            platform_operator=True,
            idempotency_key="approved-apply",
        )
        approve_change_request(row, actor=self.operator)

        result = apply_approved_change_request(row, actor=self.operator)

        self.assertTrue(result["ok"], msg=result)
        self.assertTrue(PackInstallation.objects.filter(school=self.school, pack_key="network-operator").exists())
