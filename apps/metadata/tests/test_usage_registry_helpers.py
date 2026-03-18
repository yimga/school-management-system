from unittest.mock import patch

from django.test import SimpleTestCase

from apps.metadata.usage_registry import register_usage


class MetadataUsageRegistryHelperTests(SimpleTestCase):
    def test_register_usage_swallow_soft_failures(self):
        with patch(
            "apps.metadata.models.EntityCatalogEntry.objects.get_or_create",
            side_effect=AttributeError,
        ):
            register_usage("workflow", "pack", "student", "first_name")
