from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.models import PackInstallation, PlatformEventLog
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_preview import preview_pack
from apps.schools.models import School


class PackApplyEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Pack Apply School",
            slug="pack-apply-school",
            subdomain="pack-apply-school",
            is_active=True,
            settings={"before": "value"},
        )
        self.other = School.objects.create(
            name="Other Pack Apply",
            slug="other-pack-apply",
            subdomain="other-pack-apply",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="pack_apply_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def test_apply_requires_preview_and_confirmation(self):
        preview = preview_pack("attendance-recovery", pack_type="workflow_pack", school=None)
        result = apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, preview_snapshot=preview, confirmed=True, platform_operator=True)
        self.assertFalse(result["ok"])

        result = apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, confirmed=False, platform_operator=True)
        self.assertFalse(result["ok"])
        self.assertIn("Confirmation", result["errors"][0])

    def test_apply_creates_installation_and_audits(self):
        result = apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, confirmed=True, platform_operator=True, idempotency_key="apply-pack")

        self.assertTrue(result["ok"], msg=result)
        installation = PackInstallation.objects.get(pk=result["installation_id"])
        self.assertEqual(installation.school, self.school)
        self.assertEqual(installation.status, PackInstallation.Status.APPLIED)
        self.assertTrue(installation.audit_ref)
        self.assertTrue(PlatformEventLog.objects.filter(event_type="pack_applied", tenant_id=str(self.school.pk)).exists())

    def test_apply_is_tenant_scoped_and_idempotent(self):
        first = apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, confirmed=True, platform_operator=True, idempotency_key="same-pack")
        second = apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, confirmed=True, platform_operator=True, idempotency_key="same-pack")

        self.assertTrue(first["ok"])
        self.assertTrue(second["idempotent"])
        self.other.refresh_from_db()
        self.assertNotIn("pack_installation_simulation", self.other.settings or {})

    def test_external_psp_remains_external_required(self):
        result = apply_pack("finance-approval", pack_type="policy_bundle", school=self.school, actor=self.actor, confirmed=True, platform_operator=True, idempotency_key="finance-external")

        self.assertTrue(result["ok"], msg=result)
        self.assertTrue(result["external_blockers"])
