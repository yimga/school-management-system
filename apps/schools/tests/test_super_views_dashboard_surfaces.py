"""BR-12: super_views_dashboard_surfaces re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsDashboardSurfacesReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_dashboard_surfaces_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_dashboard_surfaces as ds

        self.assertIs(super_views.super_dashboard, ds.super_dashboard)
        self.assertIs(super_views.super_dashboard_v2, ds.super_dashboard_v2)
        self.assertIs(super_views.api_super_dashboard_layout, ds.api_super_dashboard_layout)
