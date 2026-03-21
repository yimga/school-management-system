"""BR-12: super_views_command_center_views re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsCommandCenterViewsReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_command_center_views_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_command_center_views as ccv

        self.assertIs(super_views.super_command_center, ccv.super_command_center)
        self.assertIs(super_views.super_command_center_v2, ccv.super_command_center_v2)
