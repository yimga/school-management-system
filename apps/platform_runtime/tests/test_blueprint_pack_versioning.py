from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.configuration_versioning import (
    apply_pack_upgrade,
    detect_pack_upgrade,
    preview_pack_upgrade,
)
from apps.platform_runtime.models import PackInstallation
from apps.schools.models import School


class BlueprintPackVersioningTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Version School", slug="version-school", subdomain="version-school", is_active=True)
        self.actor = User.objects.create_user(username="version_actor", password="x" * 8, role=User.Role.SUPERADMIN, is_staff=True)
        self.installation = PackInstallation.objects.create(
            school=self.school,
            pack_key="network-operator",
            pack_type="dashboard_pack",
            version="0.9.0",
            installed_version="0.9.0",
            available_version="0.9.0",
            status=PackInstallation.Status.APPLIED,
            idempotency_key="old-network",
        )

    def test_upgrade_detection_and_preview_do_not_mutate_school(self):
        before = dict(self.school.settings or {})

        detected = detect_pack_upgrade(self.installation)
        preview = preview_pack_upgrade(self.installation, actor=self.actor)

        self.school.refresh_from_db()
        self.assertTrue(detected["upgrade_available"])
        self.assertEqual(self.school.settings or {}, before)
        self.assertTrue(preview["upgrade"]["upgrade_available"])

    def test_high_risk_upgrade_requires_approval(self):
        preview_pack_upgrade(self.installation, actor=self.actor)

        result = apply_pack_upgrade(self.installation, actor=self.actor, approved=False)

        self.assertFalse(result["ok"])
        self.assertIn("approval", result["errors"][0].lower())
