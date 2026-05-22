"""BR-12: super_views_dashboard_surfaces re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsDashboardSurfacesReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_dashboard_surfaces_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_dashboard_surfaces as ds

        # super_dashboard v1 retired 2026-05-22 (v3.57.12 orphan dashboard retirement);
        # super:dashboard URL routes to super_dashboard_v2 only.
        self.assertIs(super_views.super_dashboard_v2, ds.super_dashboard_v2)
        self.assertIs(super_views.api_super_dashboard_layout, ds.api_super_dashboard_layout)
