from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.models import BlueprintInstallation, PlatformEventLog
from apps.schools.models import School


class BlueprintApplyEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Apply School",
            slug="apply-school",
            subdomain="apply-school",
            is_active=True,
            settings={"before": "value"},
        )
        self.other = School.objects.create(
            name="Other Apply School",
            slug="other-apply-school",
            subdomain="other-apply-school",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="blueprint_apply_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def test_apply_requires_preview_and_confirmation(self):
        preview = preview_blueprint("private-primary-school", school=None)
        result = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            preview_snapshot=preview,
            confirmed=True,
            platform_operator=True,
        )
        self.assertFalse(result["ok"])

        preview = preview_blueprint("private-primary-school", school=self.school)
        result = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            preview_snapshot=preview,
            confirmed=False,
            platform_operator=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("Confirmation", result["errors"][0])

    def test_apply_creates_installation_and_audits(self):
        result = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="apply-primary",
        )

        self.assertTrue(result["ok"], msg=result)
        installation = BlueprintInstallation.objects.get(pk=result["installation_id"])
        self.school.refresh_from_db()
        self.assertEqual(installation.school, self.school)
        self.assertEqual(installation.status, BlueprintInstallation.Status.APPLIED)
        self.assertIn("local_first_manifest", installation.preview_snapshot)
        self.assertIn("local_first_blueprints", self.school.settings)
        self.assertEqual(
            self.school.settings["local_first_blueprints"]["private-primary-school"]["status"],
            "active",
        )
        self.assertTrue(installation.audit_ref)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="blueprint_applied",
                tenant_id=str(self.school.pk),
            ).exists()
        )

    def test_apply_is_tenant_scoped(self):
        apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="tenant-scope-primary",
        )
        self.other.refresh_from_db()
        self.assertNotIn("blueprint_marketplace", self.other.settings or {})

    def test_duplicate_apply_is_idempotent_for_same_key(self):
        first = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="same-key",
        )
        second = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="same-key",
        )

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["installation_id"], second["installation_id"])

    def test_external_psp_remains_external_required(self):
        result = apply_blueprint(
            "cameroon-gce-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="gce-external",
        )

        self.assertTrue(result["ok"], msg=result)
        self.assertIn("live_payment_collection", result["external_blockers"])

    def test_tenant_cannot_apply_operator_required_blueprint(self):
        result = apply_blueprint(
            "multi-campus-network",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=False,
        )

        self.assertFalse(result["ok"])
