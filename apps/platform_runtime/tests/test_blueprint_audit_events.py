from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.models import BlueprintInstallation, PlatformEventLog
from apps.schools.models import School


class BlueprintAuditEventsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Audit Blueprint School",
            slug="audit-blueprint-school",
            subdomain="audit-blueprint-school",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="blueprint_audit_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def test_preview_impact_apply_and_rollback_emit_audit_events(self):
        preview_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            emit_audit=True,
        )
        analyze_blueprint_impact(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            emit_audit=True,
        )
        applied = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="audit-events",
        )
        installation = BlueprintInstallation.objects.get(pk=applied["installation_id"])
        rollback_blueprint_installation(installation, actor=self.actor, confirmed=True)

        event_types = set(
            PlatformEventLog.objects.filter(tenant_id=str(self.school.pk)).values_list(
                "event_type", flat=True
            )
        )
        self.assertIn("blueprint_previewed", event_types)
        self.assertIn("blueprint_impact_viewed", event_types)
        self.assertIn("blueprint_apply_requested", event_types)
        self.assertIn("blueprint_applied", event_types)
        self.assertIn("blueprint_rollback_requested", event_types)
        self.assertIn("blueprint_rolled_back", event_types)

    def test_failed_apply_is_audited_with_actor_and_tenant(self):
        apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            preview_snapshot={"can_apply": False, "conflicts": [{"code": "forced"}]},
            confirmed=True,
            platform_operator=True,
        )

        event = PlatformEventLog.objects.filter(
            event_type="blueprint_apply_failed",
            tenant_id=str(self.school.pk),
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload["actor_id"], self.actor.pk)
        self.assertEqual(event.payload["school_id"], str(self.school.pk))

    def test_no_cross_tenant_leakage_in_audit_query(self):
        other = School.objects.create(
            name="Other Audit Blueprint School",
            slug="other-audit-blueprint-school",
            subdomain="other-audit-blueprint-school",
            is_active=True,
        )
        preview_blueprint("private-primary-school", school=self.school, emit_audit=True)
        preview_blueprint("private-primary-school", school=other, emit_audit=True)

        tenant_ids = set(
            PlatformEventLog.objects.filter(event_type="blueprint_previewed").values_list(
                "tenant_id", flat=True
            )
        )
        self.assertIn(str(self.school.pk), tenant_ids)
        self.assertIn(str(other.pk), tenant_ids)
