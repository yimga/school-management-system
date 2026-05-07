from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.models import PackInstallation, PlatformEventLog
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.pack_rollback import rollback_pack_installation
from apps.platform_runtime.pack_simulation import simulate_pack
from apps.schools.models import School


class PackAuditEventsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Pack Audit", slug="pack-audit", subdomain="pack-audit", is_active=True)
        self.actor = User.objects.create_user(username="pack_audit_actor", password="x" * 8, role=User.Role.SUPERADMIN, is_staff=True)

    def test_preview_simulation_apply_and_rollback_emit_events(self):
        preview_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, emit_audit=True)
        simulate_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, emit_audit=True)
        analyze_pack_impact("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, emit_audit=True)
        result = apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, confirmed=True, platform_operator=True, idempotency_key="audit-pack")
        installation = PackInstallation.objects.get(pk=result["installation_id"])
        rollback_pack_installation(installation, actor=self.actor, confirmed=True)

        for event_type in ["pack_previewed", "pack_simulated", "pack_impact_viewed", "pack_apply_requested", "pack_applied", "pack_rollback_requested", "pack_rolled_back"]:
            self.assertTrue(PlatformEventLog.objects.filter(event_type=event_type, tenant_id=str(self.school.pk)).exists(), event_type)

    def test_failed_apply_is_audited_with_actor_and_tenant(self):
        preview = preview_pack("attendance-recovery", pack_type="workflow_pack", school=None)
        apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, preview_snapshot=preview, confirmed=True, platform_operator=True)

        event = PlatformEventLog.objects.filter(event_type="pack_apply_failed", tenant_id=str(self.school.pk)).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload["actor_id"], self.actor.pk)
        self.assertEqual(event.payload["school_id"], str(self.school.pk))
