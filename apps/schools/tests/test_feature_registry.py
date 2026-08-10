from django.core.management import call_command
from django.test import TestCase

from apps.schools.feature_registry import (
    ensure_module_registry_seeded,
    get_available_modules,
    get_module_by_code,
    registry_module_codes,
)
from apps.siteconfig.models import FeatureToggleDefinition


class FeatureRegistryTests(TestCase):
    def test_get_available_modules_reads_db_registry(self):
        FeatureToggleDefinition.objects.filter(key__startswith="module.").delete()

        modules = get_available_modules()
        codes = {item["code"] for item in modules}

        self.assertIn("library", codes)
        self.assertTrue(
            FeatureToggleDefinition.objects.filter(key="module.library").exists()
        )
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

    # -- get_module_by_code now reads through the model overlay --------------- #
    def test_get_module_by_code_prefers_db_overlay(self):
        ensure_module_registry_seeded()
        # An operator renames a module + changes its price via the model editor.
        FeatureToggleDefinition.objects.filter(key="module.library").update(
            label="Bibliotheque", metadata={"price": "Pro"}
        )
        spec = get_module_by_code("library")
        self.assertIsNotNone(spec)
        # The overlay wins over the static FEATURE_REGISTRY "Library" / "Free".
        self.assertEqual(spec["name"], "Bibliotheque")
        self.assertEqual(spec["price"], "Pro")

    def test_get_module_by_code_falls_back_to_static_when_unseeded(self):
        FeatureToggleDefinition.objects.filter(key__startswith="module.").delete()
        spec = get_module_by_code("library")
        self.assertIsNotNone(spec)
        # No model row yet -> the code seed answers.
        self.assertEqual(spec["code"], "library")
        self.assertEqual(spec["name"], "Library")

    def test_get_module_by_code_resolves_custom_db_only_module(self):
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
        spec = get_module_by_code("custom_reports")
        self.assertIsNotNone(spec)
        self.assertEqual(spec["name"], "Custom Reports")
        self.assertEqual(spec["price"], "Pro")

    def test_get_module_by_code_unknown_returns_none(self):
        FeatureToggleDefinition.objects.filter(key__startswith="module.").delete()
        self.assertIsNone(get_module_by_code("does_not_exist"))

    # -- durable proactive seed command -------------------------------------- #
    def test_seed_feature_registry_command_populates_all_codes(self):
        FeatureToggleDefinition.objects.filter(key__startswith="module.").delete()
        call_command("seed_feature_registry")
        for code in registry_module_codes():
            self.assertTrue(
                FeatureToggleDefinition.objects.filter(
                    key=f"module.{code}", category="modules"
                ).exists(),
                f"missing FeatureToggleDefinition for module code {code!r}",
            )
        total = FeatureToggleDefinition.objects.filter(category="modules").count()
        # Idempotent: a second run creates no new rows.
        call_command("seed_feature_registry")
        self.assertEqual(
            FeatureToggleDefinition.objects.filter(category="modules").count(), total
        )
