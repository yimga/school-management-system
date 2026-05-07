from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_dependency_graph import order_installation_plan, resolve_pack_dependencies
from apps.schools.models import School


class PackDependencyGraphTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Dependency School", slug="dependency-school", subdomain="dependency-school", is_active=True)
        self.actor = User.objects.create_user(username="dependency_actor", password="x" * 8, role=User.Role.SUPERADMIN, is_staff=True)

    def test_missing_required_dependency_blocks_apply(self):
        result = apply_pack("fee-collection", pack_type="workflow_pack", school=self.school, actor=self.actor, confirmed=True, platform_operator=True)

        self.assertFalse(result["ok"])
        self.assertIn("Required pack", result["errors"][0])

    def test_recommended_dependency_warns_not_blocks(self):
        PackInstallation.objects.create(
            school=self.school,
            pack_key="money-center",
            pack_type="dashboard_pack",
            version="1.0.0",
            installed_version="1.0.0",
            available_version="1.0.0",
            status=PackInstallation.Status.APPLIED,
            idempotency_key="money-installed",
        )

        dependencies = resolve_pack_dependencies("fee-collection", pack_type="workflow_pack", school=self.school)

        self.assertIn("family-home", dependencies["recommended_missing"])
        self.assertNotIn("money-center", dependencies["missing_required_packs"])

    def test_installation_order_is_deterministic(self):
        self.assertEqual(order_installation_plan(["fee-collection", "money-center"]), ["finance-approval", "money-center", "fee-collection"])
