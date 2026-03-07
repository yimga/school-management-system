from django.test import TestCase

from apps.schools.feature_registry import get_available_modules
from apps.siteconfig.models import FeatureToggleDefinition


class FeatureRegistryTests(TestCase):
    def test_get_available_modules_reads_db_registry(self):
        FeatureToggleDefinition.objects.filter(key__startswith="module.").delete()

        modules = get_available_modules()
        codes = {item["code"] for item in modules}

        self.assertIn("library", codes)
        self.assertTrue(FeatureToggleDefinition.objects.filter(key="module.library").exists())
        self.assertTrue(
            FeatureToggleDefinition.objects.filter(
                key="module.library",
                category="modules",
                scope=FeatureToggleDefinition.Scope.SCHOOL,
            ).exists()
        )

    def test_get_available_modules_includes_custom_db_module(self):
        FeatureToggleDefinition.objects.get_or_create(
            key="module.custom_reports",
            defaults={
                "label": "Custom Reports",
                "description": "Country-specific report templates.",
                "category": "modules",
                "scope": FeatureToggleDefinition.Scope.SCHOOL,
                "default_enabled": False,
                "is_active": True,
                "metadata": {"price": "Pro"},
            },
        )
        modules = get_available_modules()
        codes = {item["code"] for item in modules}
        self.assertIn("custom_reports", codes)
