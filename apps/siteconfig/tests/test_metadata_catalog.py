from django.test import TestCase

from apps.metadata.models import EntityCatalogEntry, FieldCatalogEntry, MetadataDependency
from apps.packages.engine import apply_package, rollback
from apps.packages.models import InstalledPackage
from apps.policies.models import BlueprintPack, PolicyBundle
from apps.siteconfig.metadata_catalog import get_runtime_metadata
from apps.siteconfig.models_dashboard import DashboardPack
from apps.siteconfig.models_workflow import WorkflowPack


class RuntimeMetadataCatalogTests(TestCase):
    def test_runtime_metadata_uses_real_pack_models(self):
        BlueprintPack.objects.create(
            slug="core-secondary",
            code="core-secondary",
            name="Core Secondary",
            family="secondary",
            version="2.0",
            is_active=True,
        )
        WorkflowPack.objects.create(
            code="workflow-admissions",
            name="Admissions",
            family="admissions",
            version="1.2",
            is_active=True,
        )
        DashboardPack.objects.create(
            code="dashboard-admin",
            name="Admin Dashboard",
            family="admin",
            version="1.1",
            is_active=True,
        )
        PolicyBundle.objects.create(
            code="policy-core",
            name="Policy Core",
            version=3,
            country_scope="*",
            is_active=True,
        )

        payload = get_runtime_metadata()

        self.assertEqual(payload["blueprints"][0]["code"], "core-secondary")
        self.assertEqual(payload["workflow_packs"][0]["code"], "workflow-admissions")
        self.assertEqual(payload["dashboard_packs"][0]["code"], "dashboard-admin")
        self.assertEqual(payload["policy_bundles"][0]["code"], "policy-core")

    def test_runtime_metadata_includes_lineage_registry_and_package_rollbacks(self):
        entity = EntityCatalogEntry.objects.create(code="student", name="Student")
        field = FieldCatalogEntry.objects.create(
            entity=entity,
            field_name="admission_number",
            label="Admission Number",
            data_type="string",
        )
        MetadataDependency.objects.create(
            consumer_type="api",
            consumer_code="api:student-record",
            field=field,
        )
        MetadataDependency.objects.create(
            consumer_type="template",
            consumer_code="template:student-card",
            field=field,
        )
        MetadataDependency.objects.create(
            consumer_type="policy",
            consumer_code="policy:student-retention",
            field=field,
        )
        apply_result = apply_package(
            tenant_id=None,
            package_id="lineage-pack",
            version="2.0",
            payload_sections={
                "dashboard": {
                    "dashboards": [
                        {
                            "code": "principal-home",
                            "entity_code": "student",
                            "field_names": ["admission_number"],
                        }
                    ]
                }
            },
            actor_id=None,
        )
        installed = InstalledPackage.objects.get(pk=apply_result["installed_id"])
        rollback(installed, actor_id=None)

        payload = get_runtime_metadata()

        self.assertEqual(payload["lineage_registry"]["apis"][0]["consumer_code"], "api:student-record")
        self.assertEqual(payload["lineage_registry"]["templates"][0]["consumer_code"], "template:student-card")
        self.assertEqual(payload["lineage_registry"]["policies"][0]["consumer_code"], "policy:student-retention")
        package_entry = next(item for item in payload["package_registry"] if item["package_id"] == "lineage-pack")
        self.assertEqual(package_entry["rollback_event_count"], 1)
        self.assertGreaterEqual(package_entry["blast_radius"]["consumer_count"], 1)
