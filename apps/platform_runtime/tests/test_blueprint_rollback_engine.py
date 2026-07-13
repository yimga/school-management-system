from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.models import BlueprintInstallation, PlatformEventLog
from apps.schools.models import School


class BlueprintRollbackEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rollback School",
            slug="rollback-school",
            subdomain="rollback-school",
            is_active=True,
            settings={"original": "kept"},
        )
        self.actor = User.objects.create_user(
            username="blueprint_rollback_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        applied = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="rollback-target",
        )
        self.installation = BlueprintInstallation.objects.get(pk=applied["installation_id"])

    def test_rollback_requires_existing_installation_and_confirmation(self):
        self.assertFalse(
            rollback_blueprint_installation(
                self.installation,
                actor=self.actor,
                confirmed=False,
            )["ok"]
        )

    def test_rollback_audits_and_updates_status(self):
        result = rollback_blueprint_installation(
            self.installation,
            actor=self.actor,
            confirmed=True,
        )

        self.assertTrue(result["ok"], msg=result)
        self.installation.refresh_from_db()
        self.school.refresh_from_db()
        self.assertEqual(self.installation.status, BlueprintInstallation.Status.ROLLED_BACK)
        self.assertEqual(self.school.settings, {"original": "kept"})
        self.assertIn("offline_manifest_invalidation", result)
        self.assertIn("offline_manifest_invalidation", result["reverted_changes"])
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="blueprint_rolled_back",
                tenant_id=str(self.school.pk),
            ).exists()
        )

    def test_rollback_does_not_delete_unsafe_school_data(self):
        self.school.features = {"critical": True}
        self.school.save(update_fields=["features"])

        rollback_blueprint_installation(self.installation, actor=self.actor, confirmed=True)
        self.school.refresh_from_db()

        self.assertEqual(self.school.features, {"critical": True})

    def test_rollback_respects_tenant_isolation(self):
        other = School.objects.create(
            name="Rollback Other",
            slug="rollback-other",
            subdomain="rollback-other",
            is_active=True,
            settings={"other": "kept"},
        )

        rollback_blueprint_installation(self.installation, actor=self.actor, confirmed=True)
        other.refresh_from_db()

        self.assertEqual(other.settings, {"other": "kept"})
