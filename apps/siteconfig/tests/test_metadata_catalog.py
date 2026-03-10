from django.test import TestCase

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
