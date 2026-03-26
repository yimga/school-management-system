"""Primary horizontal nav (Wave 1) — no DB."""

from django.test import RequestFactory, SimpleTestCase

from apps.schools.control_plane_nav import (
    build_primary_control_plane_nav,
    build_tenant_operator_primary_nav,
)


class PrimaryControlPlaneNavTests(SimpleTestCase):
    """build_primary_control_plane_nav resolves 8 pills on manager urlconf."""

    def test_eight_pills_stable_order(self):
        request = RequestFactory().get("/super/dashboard/")
        request.urlconf = "config.manager_urls"
        primary = build_primary_control_plane_nav(request)
        ids = [x["id"] for x in primary]
        self.assertEqual(len(primary), 8, msg=ids)
        self.assertEqual(
            ids,
            [
                "primary_home",
                "primary_studio",
                "primary_operations",
                "primary_marketplace",
                "primary_analytics",
                "primary_migration",
                "primary_support",
                "primary_control",
            ],
        )

    def test_current_flag_studio_vs_control(self):
        req_studio = RequestFactory().get("/studio/experience/")
        req_studio.urlconf = "config.manager_urls"
        ps = {x["id"]: x for x in build_primary_control_plane_nav(req_studio)}
        self.assertTrue(ps["primary_studio"]["is_current"])
        self.assertFalse(ps["primary_control"]["is_current"])

        req_ctl = RequestFactory().get("/studio/control/")
        req_ctl.urlconf = "config.manager_urls"
        pc = {x["id"]: x for x in build_primary_control_plane_nav(req_ctl)}
        self.assertFalse(pc["primary_studio"]["is_current"])
        self.assertTrue(pc["primary_control"]["is_current"])

    def test_primary_home_highlights_ai_gateway_console(self):
        """AI gateway console lives under Platform Overview; Home pill should be current."""
        req = RequestFactory().get("/super/ai-gateway-console/")
        req.urlconf = "config.manager_urls"
        nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
        self.assertTrue(nav["primary_home"]["is_current"])
        self.assertFalse(nav["primary_operations"]["is_current"])

    def test_primary_home_highlights_trust_and_compliance(self):
        req_trust = RequestFactory().get("/super/trust/")
        req_trust.urlconf = "config.manager_urls"
        nt = {x["id"]: x for x in build_primary_control_plane_nav(req_trust)}
        self.assertTrue(nt["primary_home"]["is_current"])

        req_comp = RequestFactory().get("/super/compliance/")
        req_comp.urlconf = "config.manager_urls"
        nc = {x["id"]: x for x in build_primary_control_plane_nav(req_comp)}
        self.assertTrue(nc["primary_home"]["is_current"])

    def test_primary_analytics_highlights_billing(self):
        req = RequestFactory().get("/super/billing/")
        req.urlconf = "config.manager_urls"
        nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
        self.assertTrue(nav["primary_analytics"]["is_current"])

    def test_primary_home_highlights_schools_and_tenant_360(self):
        for path in ("/super/schools/", "/super/tenants/00000000-0000-0000-0000-000000000001/360/"):
            req = RequestFactory().get(path)
            req.urlconf = "config.manager_urls"
            nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
            self.assertTrue(nav["primary_home"]["is_current"], msg=path)
            self.assertFalse(nav["primary_control"]["is_current"], msg=path)

    def test_primary_operations_highlights_orchestration(self):
        req = RequestFactory().get("/super/orchestration/")
        req.urlconf = "config.manager_urls"
        nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
        self.assertTrue(nav["primary_operations"]["is_current"])
        self.assertFalse(nav["primary_home"]["is_current"])

    def test_primary_analytics_highlights_customer_success(self):
        req = RequestFactory().get("/super/customer-success/")
        req.urlconf = "config.manager_urls"
        nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
        self.assertTrue(nav["primary_analytics"]["is_current"])

    def test_primary_control_highlights_super_governance_and_siteconfig(self):
        for path in (
            "/super/blueprints/",
            "/super/config/feature-toggles/",
            "/siteconfig/console/",
            "/siteconfig/feature-control/",
            "/siteconfig/get-blueprints/",
            "/siteconfig/sync-center/resolve/1/",
        ):
            req = RequestFactory().get(path)
            req.urlconf = "config.manager_urls"
            nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
            self.assertTrue(nav["primary_control"]["is_current"], msg=path)
            self.assertFalse(nav["primary_studio"]["is_current"], msg=path)

    def test_primary_studio_highlights_siteconfig_brand_and_reports(self):
        for path in (
            "/siteconfig/theme-colors/",
            "/siteconfig/reports/builder/",
            "/siteconfig/preferences/",
            "/siteconfig/guided-onboarding/",
        ):
            req = RequestFactory().get(path)
            req.urlconf = "config.manager_urls"
            nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
            self.assertTrue(nav["primary_studio"]["is_current"], msg=path)
            self.assertFalse(nav["primary_control"]["is_current"], msg=path)

    def test_primary_marketplace_highlights_app_sandbox(self):
        req = RequestFactory().get("/siteconfig/app-sandbox/")
        req.urlconf = "config.manager_urls"
        nav = {x["id"]: x for x in build_primary_control_plane_nav(req)}
        self.assertTrue(nav["primary_marketplace"]["is_current"])


class TenantOperatorPrimaryNavTests(SimpleTestCase):
    """Tenant operator spine: same pill component as manager, tenant-safe URLs only."""

    def test_stable_pill_order_on_tenant_urlconf(self):
        request = RequestFactory().get("/siteconfig/feature-control/")
        request.urlconf = "config.tenant_urls"
        nav = build_tenant_operator_primary_nav(request)
        ids = [x["id"] for x in nav]
        self.assertEqual(
            ids,
            [
                "tenant_backend",
                "tenant_studio",
                "tenant_ccc",
                "tenant_feature",
                "tenant_audit",
            ],
        )

    def test_audit_vs_feature_current_flags(self):
        req_audit = RequestFactory().get("/siteconfig/feature-control/audit/")
        req_audit.urlconf = "config.tenant_urls"
        na = {x["id"]: x for x in build_tenant_operator_primary_nav(req_audit)}
        self.assertTrue(na["tenant_audit"]["is_current"])
        self.assertFalse(na["tenant_feature"]["is_current"])

        req_panel = RequestFactory().get("/siteconfig/feature-control/")
        req_panel.urlconf = "config.tenant_urls"
        np = {x["id"]: x for x in build_tenant_operator_primary_nav(req_panel)}
        self.assertTrue(np["tenant_feature"]["is_current"])
        self.assertFalse(np["tenant_audit"]["is_current"])
