"""BR-12: super_views_trust_surface re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsTrustSurfaceReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_trust_surface_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_trust_surface as trust

        self.assertIs(super_views.super_compliance_overview, trust.super_compliance_overview)
        self.assertIs(super_views.super_trust_center, trust.super_trust_center)
        self.assertIs(super_views.super_config_hub_redirect, trust.super_config_hub_redirect)
        self.assertIs(super_views.super_audit_export, trust.super_audit_export)
        self.assertIs(super_views.super_platform_events, trust.super_platform_events)
