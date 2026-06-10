"""Policies rules module smoke tests."""

from django.test import SimpleTestCase


class PoliciesRulesSmokeTests(SimpleTestCase):
    def test_module_imports(self):
        import apps.policies_rules  # noqa: F401

        self.assertTrue(True)
