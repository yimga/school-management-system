"""BR-12: super_views_support re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsSupportReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_support_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_support as support

        self.assertIs(super_views.super_support_dashboard, support.super_support_dashboard)
        self.assertIs(super_views.support_queue_fragment, support.support_queue_fragment)
        self.assertIs(super_views.support_assign_ticket, support.support_assign_ticket)
        self.assertIs(
            super_views.super_support_ticket_detail, support.super_support_ticket_detail
        )
        self.assertIs(
            super_views.super_support_csat_dashboard, support.super_support_csat_dashboard
        )
