from django.test import SimpleTestCase

from apps.platform_runtime.migration_center import apply_preview, preview_migration


class TenantMigrationBoundaryTests(SimpleTestCase):
    def test_tenant_cannot_apply_another_school_migration_preview(self):
        preview = preview_migration(
            entity="teachers",
            tenant_id="school-a",
            rows=[{"staff_number": "T1", "first_name": "Grace", "last_name": "H"}],
        )

        result = apply_preview(preview, tenant_id="school-b", actor="operator")

        self.assertFalse(result["ok"])
        self.assertIn("another school", result["errors"][0])
