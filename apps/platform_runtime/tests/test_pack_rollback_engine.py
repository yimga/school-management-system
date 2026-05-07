from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.models import PackInstallation, PlatformEventLog
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_rollback import deactivate_pack_installation, rollback_pack_installation
from apps.schools.models import School


class PackRollbackEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Pack Rollback School",
            slug="pack-rollback-school",
            subdomain="pack-rollback-school",
            is_active=True,
            settings={"before": "value"},
            features={"keep": True},
        )
        self.actor = User.objects.create_user(
            username="pack_rollback_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        result = apply_pack("attendance-recovery", pack_type="workflow_pack", school=self.school, actor=self.actor, confirmed=True, platform_operator=True, idempotency_key="rollback-pack")
        self.installation = PackInstallation.objects.get(pk=result["installation_id"])

    def test_rollback_requires_confirmation(self):
        result = rollback_pack_installation(self.installation, actor=self.actor, confirmed=False)

        self.assertFalse(result["ok"])
        self.assertTrue(PlatformEventLog.objects.filter(event_type="pack_rollback_failed").exists())

    def test_rollback_audits_and_updates_status_without_deleting_features(self):
        result = rollback_pack_installation(self.installation, actor=self.actor, confirmed=True)

        self.assertTrue(result["ok"], msg=result)
        self.installation.refresh_from_db()
        self.school.refresh_from_db()
        self.assertEqual(self.installation.status, PackInstallation.Status.ROLLED_BACK)
        self.assertEqual(self.school.features, {"keep": True})
        self.assertTrue(PlatformEventLog.objects.filter(event_type="pack_rolled_back").exists())

    def test_deactivate_updates_status(self):
        result = deactivate_pack_installation(self.installation, actor=self.actor, confirmed=True)

        self.assertTrue(result["ok"])
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.status, PackInstallation.Status.DEACTIVATED)
