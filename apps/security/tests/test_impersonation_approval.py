"""Impersonation dual-control peer approval is logged to compliance AuditLog."""

from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.compliance.models_audit import AuditLog
from apps.schools.models import School
from apps.siteconfig.models import ImpersonationLog, RegionConfig


@override_settings(
    JIT_IMPERSONATION_REQUIRE_CONSENT=True,
    IMPERSONATION_REQUIRE_JUSTIFICATION=True,
    ALLOWED_HOSTS=["*", "manager.runmycampus.com", "testserver"],
)
class ImpersonationApprovalAuditTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.region = RegionConfig.objects.first()
        if not self.region:
            self.region = RegionConfig.objects.create(
                code="CM",
                name="Cameroon",
                default_language="en",
                timezone="Africa/Douala",
            )
        self.school = School.objects.create(
            name="Approval Audit School",
            slug="approval-audit-school",
            subdomain="approval-audit-school",
            is_active=True,
            default_region=self.region,
            impersonation_consent_granted_at=timezone.now(),
            impersonation_dual_control=True,
        )
        self.actor = User.objects.create_user(
            username="approval_actor",
            email="approval.actor@example.com",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.peer = User.objects.create_user(
            username="approval_peer",
            email="approval.peer@example.com",
            password="pass12345",
            is_staff=True,
            is_superuser=False,
            role=User.Role.SUPERADMIN,
        )
        self.school.impersonation_consent_granted_by_id = self.actor.id
        self.school.save(update_fields=["impersonation_consent_granted_by_id"])

    def test_dual_control_records_compliance_approval_audit(self):
        self.client.force_login(self.actor)
        before = AuditLog.objects.filter(
            action=AuditLog.Action.APPROVE, model_name="ImpersonationSession"
        ).count()
        response = self.client.post(
            reverse("super:switch_to_tenant"),
            HTTP_HOST="manager.runmycampus.com",
            data={
                "school_id": str(self.school.id),
                "impersonation_reason": "Peer approval audit test — operator justification.",
                "peer_approver_email": "approval.peer@example.com",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("impersonate=", response.url or "")
        after = AuditLog.objects.filter(
            action=AuditLog.Action.APPROVE, model_name="ImpersonationSession"
        ).count()
        self.assertGreater(after, before)
        log = ImpersonationLog.objects.filter(
            school=self.school, action=ImpersonationLog.Action.SWITCH
        ).order_by("-created_at").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.peer_actor_id, self.peer.id)
