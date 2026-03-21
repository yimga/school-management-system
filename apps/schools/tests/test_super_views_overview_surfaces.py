"""BR-12: super_views_overview_surfaces re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsOverviewSurfacesReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_overview_surfaces_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_overview_surfaces as ovs

        self.assertIs(super_views.super_schools_list, ovs.super_schools_list)
        self.assertIs(super_views.super_analytics_overview, ovs.super_analytics_overview)
