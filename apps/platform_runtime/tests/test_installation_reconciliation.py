from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.configuration_change_requests import (
    approve_change_request,
    create_change_request,
    schedule_change_request,
)
from apps.platform_runtime.governance_queue import process_due_configuration_changes
from apps.platform_runtime.installation_reconciliation import (
    audit_installation_layers,
    reconcile_school_installations,
)
from apps.platform_runtime.models import BlueprintInstallation, ConfigurationChangeRequest
from apps.schools.models import School


class InstallationReconciliationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Reconcile School",
            slug="reconcile-school",
            subdomain="reconcile-school",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="reconcile_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )

    def test_orphan_blueprint_marker_is_audited_and_repaired(self):
        apply_result = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="reconcile-primary",
        )
        self.assertTrue(apply_result["ok"], msg=apply_result)

        installation = BlueprintInstallation.objects.get(pk=apply_result["installation_id"])
        rollback_result = rollback_blueprint_installation(
            installation, actor=self.actor, confirmed=True
        )
        self.assertTrue(rollback_result["ok"], msg=rollback_result)

        settings = dict(self.school.settings or {})
        settings.setdefault("blueprint_marketplace", {})["private-primary-school"] = {
            "status": "applied"
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings"])

        audit = audit_installation_layers(self.school)
        self.assertFalse(audit["ok"])
        self.assertTrue(
            any(f["code"] == "orphan_blueprint_settings_marker" for f in audit["findings"])
        )

        repair = reconcile_school_installations(
            self.school, repair=True, context="test"
        )
        self.assertTrue(repair["ok"])
        self.assertTrue(repair.get("repaired"))

    def test_scheduled_blueprint_rollback_runs_when_due(self):
        apply_result = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="rollback-sched-primary",
        )
        self.assertTrue(apply_result["ok"], msg=apply_result)

        row = create_change_request(
            ConfigurationChangeRequest.RequestType.BLUEPRINT_ROLLBACK,
            target_key="private-primary-school",
            target_type="blueprint",
            school=self.school,
            actor=self.actor,
            platform_operator=True,
            idempotency_key="rollback-sched-req",
        )
        approve_change_request(row, actor=self.actor)
        schedule_change_request(
            row,
            actor=self.actor,
            scheduled_at=timezone.now() - timedelta(minutes=1),
        )

        batch = process_due_configuration_changes(limit=10)
        self.assertEqual(batch["processed"], 1)
        self.assertTrue(batch["results"][0]["ok"])

        row.refresh_from_db()
        self.assertEqual(row.status, ConfigurationChangeRequest.Status.ROLLED_BACK)
        self.assertFalse(
            BlueprintInstallation.objects.filter(
                school=self.school,
                blueprint_key="private-primary-school",
                status=BlueprintInstallation.Status.APPLIED,
            ).exists()
        )
