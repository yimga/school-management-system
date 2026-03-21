"""BR-12: super_views_school_api re-exported from super_views for URL compatibility."""

from django.test import SimpleTestCase


class SuperViewsSchoolApiReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_school_api_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_school_api as school_api

        pairs = [
            ("api_school_timeline", school_api.api_school_timeline),
            ("api_approve_school", school_api.api_approve_school),
            ("school_lifecycle_action", school_api.school_lifecycle_action),
            ("api_school_policy_bundles", school_api.api_school_policy_bundles),
            ("api_school_policy_bundle_activate", school_api.api_school_policy_bundle_activate),
        ]
        for name, fn in pairs:
            with self.subTest(name=name):
                self.assertIs(getattr(super_views, name), fn)
