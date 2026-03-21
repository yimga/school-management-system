"""BR-12: super_views_platform_monitoring re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsPlatformMonitoringReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_platform_monitoring_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_platform_monitoring as mon

        self.assertIs(super_views.super_usage, mon.super_usage)
        self.assertIs(super_views.super_pulse, mon.super_pulse)
        self.assertIs(super_views.super_tenant_health, mon.super_tenant_health)
        self.assertIs(super_views.super_tenant_360, mon.super_tenant_360)
        self.assertIs(
            super_views.super_control_health_dashboard,
            mon.super_control_health_dashboard,
        )
