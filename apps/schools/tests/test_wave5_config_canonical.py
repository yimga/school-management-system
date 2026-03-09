"""
Wave 5 tests: configuration and canonical model alignment.

Non-negotiable: tenant behavior from Policy/Blueprint/registry; no hardcoded region in core defaults.
"""
from django.test import TestCase


class Wave5PlatformDefaultsTests(TestCase):
    """Wave 5.3: Platform defaults used instead of hardcoded region/currency."""

    def test_get_platform_defaults_exists(self):
        """get_platform_defaults must exist for tenant fallbacks."""
        from apps.platform_runtime.helpers import get_platform_defaults
        defaults = get_platform_defaults()
        self.assertIsInstance(defaults, dict)
        self.assertIn("currency", defaults)
        self.assertIn("region_code", defaults)

    def test_policy_resolver_no_hardcoded_region_currency(self):
        """Policy resolver must not hardcode CMR/XAF (use platform defaults or registry)."""
        from apps.policies import resolver
        import inspect
        source = inspect.getsource(resolver.get_effective_policy)
        self.assertNotIn('"CMR"', source)
        self.assertNotIn("'CMR'", source)
        self.assertNotIn('"XAF"', source)
        self.assertNotIn("'XAF'", source)


class Wave5CanonicalObjectsTests(TestCase):
    """Wave 5.2: Key canonical objects exist (School, BlueprintPack, PolicyBundle)."""

    def test_school_model_exists(self):
        from apps.schools.models import School
        self.assertTrue(hasattr(School, "settings_json") or hasattr(School, "features"))

    def test_blueprint_pack_exists(self):
        from apps.policies.models import BlueprintPack
        self.assertTrue(hasattr(BlueprintPack, "version"))

    def test_policy_bundle_exists(self):
        from apps.policies.models import PolicyBundle
        self.assertTrue(hasattr(PolicyBundle, "version"))
