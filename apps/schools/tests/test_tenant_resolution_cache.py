"""AWS pillar: versioned tenant resolution cache keys."""

from django.test import SimpleTestCase

from apps.schools.middleware import _tenant_cache_key
from apps.schools.tenant_resolution_cache import tenant_resolution_cache_key


class TenantResolutionCacheTests(SimpleTestCase):
    def test_key_is_versioned_and_normalized(self):
        key = tenant_resolution_cache_key("Demo.School.COM", "host")
        self.assertTrue(key.startswith("rmc:v1:tenant_resolve:host:"))
        self.assertIn("demo.school.com", key)

    def test_middleware_alias_matches_module(self):
        self.assertEqual(
            _tenant_cache_key("acme", "subdomain"),
            tenant_resolution_cache_key("acme", "subdomain"),
        )

    def test_unknown_kind_defaults_to_host(self):
        key = tenant_resolution_cache_key("x", "invalid")
        self.assertIn(":host:", key)
