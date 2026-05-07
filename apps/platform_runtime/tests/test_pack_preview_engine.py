from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_preview import preview_pack
from apps.schools.models import School


class PackPreviewEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Pack Preview School",
            slug="pack-preview-school",
            subdomain="pack-preview-school",
            is_active=True,
            settings={"before": "value"},
        )

    def test_preview_does_not_mutate_db(self):
        before_settings = dict(self.school.settings)
        before_count = PackInstallation.objects.count()

        result = preview_pack("attendance-recovery", pack_type="workflow_pack", school=self.school)

        self.assertTrue(result["can_apply"])
        self.school.refresh_from_db()
        self.assertEqual(self.school.settings, before_settings)
        self.assertEqual(PackInstallation.objects.count(), before_count)

    def test_pack_types_include_expected_sections(self):
        workflow = preview_pack("attendance-recovery", pack_type="workflow_pack", school=self.school)
        dashboard = preview_pack("school-command-center", pack_type="dashboard_pack", school=self.school)
        policy = preview_pack("finance-approval", pack_type="policy_bundle", school=self.school)

        self.assertTrue(workflow["affected_workflows"])
        self.assertTrue(dashboard["affected_dashboards"])
        self.assertTrue(policy["affected_policies"])

    def test_external_dependencies_remain_external_required(self):
        result = preview_pack("finance-approval", pack_type="policy_bundle", school=self.school)

        self.assertTrue(result["external_required"])
        self.assertIn("External dependencies", result["warnings"][0])

    def test_conflicts_block_apply_without_tenant(self):
        result = preview_pack("attendance-recovery", pack_type="workflow_pack", school=None)

        self.assertFalse(result["can_apply"])
        self.assertEqual(result["conflicts"][0]["code"], "tenant_required")

    def test_tenant_isolation_preview_names_only_target_tenant(self):
        other = School.objects.create(
            name="Other Pack Preview",
            slug="other-pack-preview",
            subdomain="other-pack-preview",
            is_active=True,
        )

        result = preview_pack("attendance-recovery", pack_type="workflow_pack", school=self.school)

        self.assertEqual(result["tenant"], str(self.school.pk))
        self.assertNotEqual(result["tenant"], str(other.pk))
