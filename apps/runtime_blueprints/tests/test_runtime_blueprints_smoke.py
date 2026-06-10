"""Runtime blueprints module smoke tests."""

from django.test import SimpleTestCase


class RuntimeBlueprintsSmokeTests(SimpleTestCase):
    def test_module_imports(self):
        import apps.runtime_blueprints  # noqa: F401

        self.assertTrue(True)
