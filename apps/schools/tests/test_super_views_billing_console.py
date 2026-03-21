"""BR-12: super_views_billing_console re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsBillingConsoleReexportTests(SimpleTestCase):
    def test_super_views_alias_matches_billing_console_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_billing_console as bill

        self.assertIs(super_views.billing_dashboard, bill.billing_dashboard)
