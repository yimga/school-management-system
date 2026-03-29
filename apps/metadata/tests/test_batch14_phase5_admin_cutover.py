"""Batch 14 Phase 5: canonical metadata.DynamicField* on tenant + platform admin sites."""

from django.test import SimpleTestCase

from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from config.admin import platform_admin_site, tenant_admin_site


class Batch14Phase5MetadataDynamicFieldAdminTests(SimpleTestCase):
    def test_metadata_dynamicfield_registered_on_tenant_and_platform_admin(self):
        self.assertIn(DynamicFieldDefinition, tenant_admin_site._registry)
        self.assertIn(DynamicFieldValue, tenant_admin_site._registry)
        self.assertIn(DynamicFieldDefinition, platform_admin_site._registry)
        self.assertIn(DynamicFieldValue, platform_admin_site._registry)
