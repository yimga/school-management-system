"""BR-12: super_views_exports re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsExportsReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_exports_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_exports as ex

        self.assertIs(super_views.export_schools_csv, ex.export_schools_csv)
        self.assertIs(super_views.export_super_dashboard_pdf, ex.export_super_dashboard_pdf)
        self.assertIs(super_views.export_revenue_csv, ex.export_revenue_csv)
