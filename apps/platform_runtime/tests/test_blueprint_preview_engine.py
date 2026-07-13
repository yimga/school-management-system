from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.blueprint_contract import (
    LOCAL_FIRST_MANIFEST_REQUIRED_FIELDS,
    list_blueprints,
)
from apps.platform_runtime.blueprint_preview import (
    preview_blueprint,
    preview_mutation_fingerprint,
)
from apps.schools.models import School


class BlueprintPreviewEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Preview School",
            slug="preview-school",
            subdomain="preview-school",
            is_active=True,
            settings={"existing": "kept"},
        )

    def test_preview_returns_expected_sections(self):
        preview = preview_blueprint("private-primary-school", school=self.school)

        self.assertTrue(preview["can_apply"])
        self.assertEqual(preview["blueprint_key"], "private-primary-school")
        self.assertIn("changes", preview)
        self.assertIn("rollback_plan", preview)
        self.assertIn("audit_summary", preview)
        self.assertIn("local_first_manifest", preview)
        self.assertIn("offline_readiness", preview)
        self.assertIn("outage_survival_matrix", preview)
        self.assertTrue(any(row["section"] == "module" for row in preview["changes"]))
        self.assertTrue(
            any(row["section"] == "local_first_manifest" for row in preview["changes"])
        )

    def test_tenant_safe_blueprints_have_complete_local_first_manifest(self):
        for blueprint in list_blueprints(tenant_safe_only=True):
            with self.subTest(blueprint=blueprint["key"]):
                manifest = blueprint["local_first_manifest"]
                for field in LOCAL_FIRST_MANIFEST_REQUIRED_FIELDS:
                    self.assertIn(field, manifest)

    def test_preview_does_not_mutate_database_or_school_settings(self):
        before = preview_mutation_fingerprint(self.school)
        preview_blueprint("private-primary-school", school=self.school)
        self.school.refresh_from_db()
        after = preview_mutation_fingerprint(self.school)

        self.assertEqual(before, after)

    def test_external_psp_items_are_marked_external_required(self):
        preview = preview_blueprint("cameroon-gce-school", school=self.school)

        self.assertIn("live_payment_collection", preview["external_required"])
        self.assertTrue(any("External dependencies" in w for w in preview["warnings"]))
        self.assertEqual(
            preview["offline_readiness"]["status"],
            "READY_WITH_EXTERNAL_BLOCKERS",
        )

    def test_conflicts_block_apply(self):
        preview = preview_blueprint("private-primary-school", school=None)

        self.assertFalse(preview["can_apply"])
        self.assertIn("tenant_required", {c["code"] for c in preview["conflicts"]})

    def test_tenant_isolation_preview_uses_only_selected_school(self):
        other = School.objects.create(
            name="Other Preview School",
            slug="other-preview-school",
            subdomain="other-preview-school",
            is_active=True,
        )

        preview = preview_blueprint("private-primary-school", school=self.school)

        self.assertEqual(preview["tenant"], str(self.school.pk))
        self.assertNotEqual(preview["tenant"], str(other.pk))
