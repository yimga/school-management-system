"""BR-12: super_views_policy re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsPolicyReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_policy_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_policy as policy

        self.assertIs(super_views.super_policy_diff, policy.super_policy_diff)
        self.assertIs(
            super_views.super_apply_policy_bundle_to_sandbox,
            policy.super_apply_policy_bundle_to_sandbox,
        )
