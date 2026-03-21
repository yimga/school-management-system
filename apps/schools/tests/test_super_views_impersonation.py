"""BR-12: super_views_impersonation re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsImpersonationReexportTests(SimpleTestCase):
    def test_super_views_alias_matches_impersonation_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_impersonation as imp

        self.assertIs(super_views.switch_to_tenant, imp.switch_to_tenant)
