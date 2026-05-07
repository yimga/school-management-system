from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.models import BlueprintInstallation, PackInstallation
from apps.schools.models import School


class BlueprintPackIntegrationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Blueprint Packs", slug="blueprint-packs", subdomain="blueprint-packs", is_active=True)
        self.actor = User.objects.create_user(username="blueprint_pack_actor", password="x" * 8, role=User.Role.SUPERADMIN, is_staff=True)

    def test_blueprint_preview_includes_pack_summaries(self):
        preview = preview_blueprint("private-primary-school", school=self.school, actor=self.actor, platform_operator=True)

        self.assertTrue(preview["pack_previews"])
        self.assertTrue(preview["pack_simulation_readiness"])
        self.assertTrue(preview["pack_impact_results"])
        self.assertFalse(preview["pack_install_blockers"])

    def test_blueprint_apply_creates_linked_pack_installations(self):
        result = apply_blueprint("private-primary-school", school=self.school, actor=self.actor, confirmed=True, platform_operator=True, idempotency_key="blueprint-pack-link")

        self.assertTrue(result["ok"], msg=result)
        blueprint_installation = BlueprintInstallation.objects.get(pk=result["installation_id"])
        self.assertTrue(PackInstallation.objects.filter(blueprint_installation=blueprint_installation).exists())
        self.assertTrue(result["pack_installations"])
