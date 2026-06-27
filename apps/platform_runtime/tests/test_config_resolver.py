"""Wave A: unit tests for the single keyed config resolver (no DB).

Proves get_effective_config delegates to the ONE cached resolver
(get_effective_site_settings) rather than re-implementing precedence, and is
fail-soft. SimpleTestCase + mock so it runs in any lane.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_runtime.config_resolver import (
    get_config_owner,
    get_effective_config,
)


class GetEffectiveConfigTests(SimpleTestCase):
    def test_returns_attribute_from_the_cached_resolver(self):
        site = SimpleNamespace(primary_color="#123456", site_name="Demo")
        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings",
            return_value=site,
        ) as resolver:
            self.assertEqual(get_effective_config(object(), "primary_color"), "#123456")
            self.assertEqual(get_effective_config(object(), "site_name"), "Demo")
        # Delegated to the one resolver, not a second ORM path.
        self.assertTrue(resolver.called)

    def test_unknown_key_returns_default(self):
        site = SimpleNamespace(primary_color="#123456")
        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings",
            return_value=site,
        ):
            self.assertIsNone(get_effective_config(object(), "nope"))
            self.assertEqual(
                get_effective_config(object(), "nope", default="fallback"), "fallback"
            )

    def test_none_site_is_fail_soft(self):
        # The resolver can legitimately return None (boot / broken singleton).
        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings",
            return_value=None,
        ):
            self.assertEqual(
                get_effective_config(object(), "primary_color", default="d"), "d"
            )

    def test_empty_key_returns_default_without_calling_resolver(self):
        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings"
        ) as resolver:
            self.assertEqual(get_effective_config(object(), "", default="d"), "d")
        self.assertFalse(resolver.called)

    def test_precedence_is_inherited_not_reimplemented(self):
        # The merged object already reflects School.settings precedence; the
        # resolver just reads the merged value. A school-overridden field shows
        # the overridden value because get_effective_site_settings merged it.
        merged = SimpleNamespace(term_count=3)  # e.g. school overrode platform default
        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings",
            return_value=merged,
        ):
            self.assertEqual(get_effective_config(object(), "term_count"), 3)


class GetConfigOwnerTests(SimpleTestCase):
    def test_delegates_to_classify_site_settings_field(self):
        with patch(
            "apps.siteconfig.domain_ownership.classify_site_settings_field",
            return_value="brand_experience",
        ) as classify:
            self.assertEqual(get_config_owner("primary_color"), "brand_experience")
        classify.assert_called_once_with("primary_color")
