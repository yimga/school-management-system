"""
Phase D: Tests for Plan model, is_feature_enabled (plan + addons), and Feature Gatekeeper middleware.
"""

import json

from django.test import TestCase, RequestFactory, tag
from django.http import HttpResponse

from apps.schools.models import (
    School,
    is_feature_enabled,
    is_plan_entitlement_feature_enabled,
)
from apps.platform_runtime.models import PlatformReportPlatformSkuDefault
from apps.siteconfig.models import Plan
from apps.schools.rls_context import rls_bypass, rls_school


class PlanModelTests(TestCase):
    """Plan model creation and defaults."""

    def test_plan_create(self):
        plan = Plan.objects.create(
            name="Basic",
            slug="basic",
            max_students=500,
            max_staff=50,
            included_features=["library", "transport"],
            billing_model=Plan.BillingModel.FLAT,
            base_price=100,
        )
        self.assertEqual(plan.slug, "basic")
        self.assertEqual(plan.max_students, 500)
        self.assertIn("library", plan.included_features)
        self.assertIn("transport", plan.included_features)

    def test_plan_billing_models(self):
        plan = Plan.objects.create(
            name="Pro",
            slug="pro",
            billing_model=Plan.BillingModel.PER_STUDENT,
            price_per_student=2,
        )
        self.assertEqual(plan.billing_model, "PER_STUDENT")
        self.assertEqual(plan.price_per_student, 2)


@tag("tenants_rls")
class UsageLimitMiddlewareTests(TestCase):
    def test_max_students_limit_blocks_when_at_cap(self):
        from apps.people.models import StudentProfile
        from apps.schools.middleware import UsageLimitMiddleware

        factory = RequestFactory()
        with rls_bypass():
            plan = Plan.objects.create(
                name="Seat capped",
                slug="seat-capped",
                max_students=1,
                included_features=["reports"],
                is_active=True,
            )
            school = School.objects.create(
                name="Seat cap school",
                slug="seat-cap-school",
                subdomain="seat-cap-school",
                is_active=True,
                plan=plan,
            )
            StudentProfile.objects.create(
                school=school,
                first_name="Ada",
                last_name="Cap",
                student_code="CAP-001",
            )
        request = factory.get("/api/students/", HTTP_ACCEPT="application/json")
        request.school = school
        middleware = UsageLimitMiddleware(lambda r: HttpResponse("ok"))

        with rls_school(school.id):
            response = middleware.process_request(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.content)["limit"], "max_students")


class IsFeatureEnabledTests(TestCase):
    """is_feature_enabled(tenant, code) considers plan.included_features, addons, then School.features."""

    def setUp(self):
        self.plan = Plan.objects.create(
            name="Basic",
            slug="basic",
            included_features=["library", "reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Test School",
            slug="test-school",
            subdomain="test-school",
            is_active=True,
            plan=self.plan,
            addons=["design_studio"],
            features={"cahier_de_texte": True},
        )

    def test_feature_from_plan_included(self):
        self.assertTrue(is_feature_enabled(self.school, "library"))
        self.assertTrue(is_feature_enabled(self.school, "reports"))

    def test_feature_from_addons(self):
        self.assertTrue(is_feature_enabled(self.school, "design_studio"))

    def test_feature_from_school_features_fallback(self):
        # cahier_de_texte is in School.features; resolve_module_enabled may also be used
        self.assertTrue(is_feature_enabled(self.school, "cahier_de_texte"))

    def test_feature_not_enabled(self):
        self.assertFalse(is_feature_enabled(self.school, "nonexistent_module"))

    def test_none_school_returns_false(self):
        self.assertFalse(is_feature_enabled(None, "library"))

    def test_school_no_plan_uses_fallback(self):
        school_no_plan = School.objects.create(
            name="No Plan School",
            slug="no-plan",
            subdomain="no-plan",
            is_active=True,
            plan=None,
            features={"my_feature": True},
        )
        # Should fall back to _has_feature_fallback (School.features + resolve_module_enabled)
        self.assertTrue(is_feature_enabled(school_no_plan, "my_feature"))


class PlanEntitlementVsIsFeatureEnabledTests(TestCase):
    """
    SKU-style gates use is_plan_entitlement_feature_enabled; is_feature_enabled also folds in
    BASE_SCHOOL required_apps via get_tenant_modules when the school has no TenantSystem rows.
    """

    def test_reports_enabled_by_manifest_but_not_plan_entitlement(self):
        plan = Plan.objects.create(
            name="Lite manifest contrast",
            slug="lite-manifest-contrast",
            included_features=["library"],
            is_active=True,
        )
        school = School.objects.create(
            name="Manifest contrast school",
            slug="manifest-contrast-school",
            subdomain="manifest-contrast-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertFalse(
            is_plan_entitlement_feature_enabled(school, "reports"),
            "Plan SKUs omit reports — ministry gates must not treat manifest as entitlement.",
        )
        self.assertTrue(
            is_feature_enabled(school, "reports"),
            "BASE_SCHOOL module manifest still lists reports in required_apps for empty TenantSystem.",
        )

    def test_custom_builder_gate_uses_plan_entitlement_not_manifest_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        factory = RequestFactory()
        plan = Plan.objects.create(
            name="Lite manifest custom builder",
            slug="lite-manifest-cb",
            included_features=["library"],
            is_active=True,
        )
        school = School.objects.create(
            name="Manifest CB school",
            slug="manifest-cb-school",
            subdomain="manifest-cb-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertTrue(is_feature_enabled(school, "reports"))
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "reports"))
        self.assertFalse(
            is_plan_entitlement_feature_enabled(school, "reports_custom_builder"),
        )
        request = factory.get("/siteconfig/reports/builder/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_scheduled_hub_uses_plan_entitlement_not_manifest_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        factory = RequestFactory()
        plan = Plan.objects.create(
            name="Lite manifest scheduled",
            slug="lite-manifest-sd",
            included_features=["library"],
            is_active=True,
        )
        school = School.objects.create(
            name="Manifest SD school",
            slug="manifest-sd-school",
            subdomain="manifest-sd-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertTrue(is_feature_enabled(school, "reports"))
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "reports_scheduled_delivery"))
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "reports"))
        request = factory.get("/siteconfig/reports/scheduled/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)


class AnalyticsTenantAppGateTests(TestCase):
    """Intelligence SKU: /analytics/* requires explicit analytics entitlement (not manifest-only)."""

    def test_analytics_dashboard_403_without_entitlement(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        factory = RequestFactory()
        plan = Plan.objects.create(
            name="Core only",
            slug="core-only-analytics-gate",
            included_features=["library", "reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="No analytics school",
            slug="no-analytics-school",
            subdomain="no-analytics-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "analytics"))
        request = factory.get("/analytics/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw.process_request(request).status_code, 403)

    def test_analytics_master_sheet_allowed_with_entitlement(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        factory = RequestFactory()
        plan = Plan.objects.create(
            name="Intelligence",
            slug="intel-analytics-gate",
            included_features=["library", "analytics"],
            is_active=True,
        )
        school = School.objects.create(
            name="Analytics school",
            slug="analytics-school",
            subdomain="analytics-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertTrue(is_plan_entitlement_feature_enabled(school, "analytics"))
        request = factory.get("/analytics/master-sheet/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertIsNone(mw.process_request(request))


class OperatorReportPlatformBundleFloorTests(TestCase):
    """
    Platform ``PlatformReportPlatformSkuDefault`` floors granular report-platform codes
    when plan/addons/features already include coarse ``reports``.
    """

    def tearDown(self):
        PlatformReportPlatformSkuDefault.objects.all().delete()

    def test_operator_advanced_floor_when_plan_has_coarse_reports_only(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug="reports-advanced"
        )
        plan = Plan.objects.create(
            name="Reports SKU floor",
            slug="reports-sku-floor",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Floor school",
            slug="floor-school",
            subdomain="floor-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertTrue(
            is_plan_entitlement_feature_enabled(school, "reports_ministry_exports")
        )
        self.assertTrue(
            is_plan_entitlement_feature_enabled(school, "reports_custom_builder")
        )

    def test_operator_standard_floor_excludes_ministry_exports(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug="reports-standard"
        )
        plan = Plan.objects.create(
            name="Reports standard floor",
            slug="reports-standard-floor",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Std floor school",
            slug="std-floor-school",
            subdomain="std-floor-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertFalse(
            is_plan_entitlement_feature_enabled(school, "reports_ministry_exports")
        )
        self.assertTrue(
            is_plan_entitlement_feature_enabled(school, "reports_pdf_exports")
        )

    def test_no_operator_singleton_no_granular_floor(self):
        plan = Plan.objects.create(
            name="Reports no floor",
            slug="reports-no-floor",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="No floor school",
            slug="no-floor-school",
            subdomain="no-floor-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        self.assertFalse(
            is_plan_entitlement_feature_enabled(school, "reports_ministry_exports")
        )
        self.assertFalse(
            is_plan_entitlement_feature_enabled(school, "reports_pdf_exports")
        )

    def test_tenant_slug_overrides_operator_advanced_down_to_standard(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug="reports-advanced"
        )
        plan = Plan.objects.create(
            name="Reports override down",
            slug="reports-override-down",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Override down school",
            slug="override-down-school",
            subdomain="override-down-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
            report_platform_bundle_slug="reports-standard",
        )
        self.assertFalse(
            is_plan_entitlement_feature_enabled(school, "reports_ministry_exports")
        )
        self.assertTrue(
            is_plan_entitlement_feature_enabled(school, "reports_pdf_exports")
        )

    def test_tenant_slug_overrides_operator_standard_up_to_advanced(self):
        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug="reports-standard"
        )
        plan = Plan.objects.create(
            name="Reports override up",
            slug="reports-override-up",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Override up school",
            slug="override-up-school",
            subdomain="override-up-school",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
            report_platform_bundle_slug="reports-advanced",
        )
        self.assertTrue(
            is_plan_entitlement_feature_enabled(school, "reports_ministry_exports")
        )


class FeatureGatekeeperMiddlewareTests(TestCase):
    """FeatureGatekeeperMiddleware returns 403 when path requires a feature the school doesn't have."""

    def setUp(self):
        self.factory = RequestFactory()
        self.plan = Plan.objects.create(
            name="Basic",
            slug="basic",
            included_features=["library"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Test School",
            slug="test-school",
            subdomain="test-school",
            is_active=True,
            plan=self.plan,
            addons=[],
            features={},
        )

    def test_middleware_skips_when_no_school(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        request = self.factory.get("/portal/design-studio/")
        request.school = None
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        resp = mw(request)
        self.assertEqual(resp.status_code, 200)

    def test_middleware_skips_when_path_not_in_map(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        request = self.factory.get("/some/other/path/")
        request.school = self.school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        resp = mw(request)
        self.assertEqual(resp.status_code, 200)

    def test_middleware_403_when_path_gated_and_feature_disabled(self):
        from apps.schools.middleware import (
            FeatureGatekeeperMiddleware,
            FEATURE_GATE_PATH_MAP,
        )

        # Temporarily add a path that requires design_studio (school doesn't have it)
        original = dict(FEATURE_GATE_PATH_MAP)
        try:
            FEATURE_GATE_PATH_MAP["/portal/design-studio/"] = "design_studio"
            request = self.factory.get("/portal/design-studio/")
            request.school = self.school
            mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
            resp = mw(request)
            self.assertEqual(resp.status_code, 403)
        finally:
            FEATURE_GATE_PATH_MAP.clear()
            FEATURE_GATE_PATH_MAP.update(original)

    def test_middleware_200_when_path_gated_and_feature_enabled(self):
        from apps.schools.middleware import (
            FeatureGatekeeperMiddleware,
            FEATURE_GATE_PATH_MAP,
        )

        self.school.addons = ["design_studio"]
        self.school.save()
        original = dict(FEATURE_GATE_PATH_MAP)
        try:
            FEATURE_GATE_PATH_MAP["/portal/design-studio/"] = "design_studio"
            request = self.factory.get("/portal/design-studio/")
            request.school = self.school
            mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
            resp = mw(request)
            self.assertEqual(resp.status_code, 200)
        finally:
            FEATURE_GATE_PATH_MAP.clear()
            FEATURE_GATE_PATH_MAP.update(original)


class ReportMinistryFeatureGateAnyOfTests(TestCase):
    """Batch 14+: ministry-oriented report URLs require granular or coarse reports capability."""

    def setUp(self):
        self.factory = RequestFactory()
        self.plan_no_reports = Plan.objects.create(
            name="Lite",
            slug="gate-lite",
            included_features=["library"],
            is_active=True,
        )
        self.plan_coarse_reports = Plan.objects.create(
            name="Std",
            slug="gate-std",
            included_features=["reports"],
            is_active=True,
        )
        self.plan_ministry_only = Plan.objects.create(
            name="Ministry SKU",
            slug="gate-ministry",
            included_features=["reports_ministry_exports"],
            is_active=True,
        )

    def test_regulatory_export_403_without_reports_capabilities(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="NR",
            slug="gate-nr",
            subdomain="gate-nr",
            is_active=True,
            plan=self.plan_no_reports,
        )
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "reports"))
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "reports_ministry_exports"))
        request = self.factory.get("/reports/regulatory-export/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_regulatory_export_200_with_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="CR",
            slug="gate-cr",
            subdomain="gate-cr",
            is_active=True,
            plan=self.plan_coarse_reports,
        )
        request = self.factory.get("/reports/regulatory-export/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)

    def test_statistical_return_200_with_granular_ministry_exports_only(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="ME",
            slug="gate-me",
            subdomain="gate-me",
            is_active=True,
            plan=self.plan_ministry_only,
        )
        request = self.factory.get("/reports/statistical-return/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)


class ReportMinistryApiFeatureGateAnyOfTests(TestCase):
    """v1 API ministry / EMIS routes use the same entitlement codes as HTML ministry exports."""

    def setUp(self):
        self.factory = RequestFactory()
        self.plan_no_reports = Plan.objects.create(
            name="Lite API",
            slug="gate-api-lite",
            included_features=["library"],
            is_active=True,
        )
        self.plan_coarse_reports = Plan.objects.create(
            name="Std API",
            slug="gate-api-std",
            included_features=["reports"],
            is_active=True,
        )
        self.plan_ministry_only = Plan.objects.create(
            name="Ministry API SKU",
            slug="gate-api-ministry",
            included_features=["reports_ministry_exports"],
            is_active=True,
        )

    def test_regulatory_presets_api_403_without_entitlement(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="NAPI",
            slug="gate-napi",
            subdomain="gate-napi",
            is_active=True,
            plan=self.plan_no_reports,
        )
        request = self.factory.get("/api/v1/reports/regulatory-presets")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_regulatory_export_api_200_with_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="CAPI",
            slug="gate-capi",
            subdomain="gate-capi",
            is_active=True,
            plan=self.plan_coarse_reports,
        )
        request = self.factory.post("/api/v1/reports/regulatory-export")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)

    def test_emis_prepare_api_200_with_granular_ministry_only(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="EAPI",
            slug="gate-eapi",
            subdomain="gate-eapi",
            is_active=True,
            plan=self.plan_ministry_only,
        )
        request = self.factory.post("/api/v1/reports/emis/prepare")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)


class ReportStaffPublishPlanGateTests(TestCase):
    """Staff report publisher URLs require coarse ``reports`` on the billing plan (not manifest-only)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.plan_no_reports = Plan.objects.create(
            name="Lite staff",
            slug="gate-staff-lite",
            included_features=["library"],
            is_active=True,
        )
        self.plan_reports = Plan.objects.create(
            name="Std staff",
            slug="gate-staff-std",
            included_features=["reports"],
            is_active=True,
        )

    def test_publish_403_without_reports_on_plan(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="NP",
            slug="gate-np",
            subdomain="gate-np",
            is_active=True,
            plan=self.plan_no_reports,
        )
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "reports"))
        request = self.factory.get("/reports/publish/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_promotion_preview_200_when_plan_includes_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="PR",
            slug="gate-pr",
            subdomain="gate-pr",
            is_active=True,
            plan=self.plan_reports,
        )
        request = self.factory.get("/reports/promotion-preview/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)


class ReportParentPdfExportFeatureGateAnyOfTests(TestCase):
    """Batch 14+: parent report download URLs require granular or coarse reports capability."""

    def setUp(self):
        self.factory = RequestFactory()
        self.plan_no_reports = Plan.objects.create(
            name="Lite PDF",
            slug="gate-pdf-lite",
            included_features=["library"],
            is_active=True,
        )
        self.plan_coarse_reports = Plan.objects.create(
            name="Std PDF",
            slug="gate-pdf-std",
            included_features=["reports"],
            is_active=True,
        )
        self.plan_pdf_exports_only = Plan.objects.create(
            name="PDF SKU",
            slug="gate-pdf-sku",
            included_features=["reports_pdf_exports"],
            is_active=True,
        )

    def test_parent_report_403_without_pdf_or_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="NPDF",
            slug="gate-npdf",
            subdomain="gate-npdf",
            is_active=True,
            plan=self.plan_no_reports,
        )
        self.assertFalse(is_plan_entitlement_feature_enabled(school, "reports_pdf_exports"))
        request = self.factory.get("/reports/parent/report/42/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_parent_report_200_with_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="CRPDF",
            slug="gate-crpdf",
            subdomain="gate-crpdf",
            is_active=True,
            plan=self.plan_coarse_reports,
        )
        request = self.factory.get("/reports/parent/report/99/annual/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)

    def test_parent_report_200_with_granular_pdf_exports_only(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="PE",
            slug="gate-pe",
            subdomain="gate-pe",
            is_active=True,
            plan=self.plan_pdf_exports_only,
        )
        request = self.factory.get("/reports/parent/report/7/csv/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)


class ReportCustomBuilderFeatureGateAnyOfTests(TestCase):
    """Batch 14+: report card builder / previews and API ad-hoc reports need granular or coarse reports."""

    def setUp(self):
        self.factory = RequestFactory()
        self.plan_no_reports = Plan.objects.create(
            name="Lite CB",
            slug="gate-cb-lite",
            included_features=["library"],
            is_active=True,
        )
        self.plan_coarse_reports = Plan.objects.create(
            name="Std CB",
            slug="gate-cb-std",
            included_features=["reports"],
            is_active=True,
        )
        self.plan_custom_builder_only = Plan.objects.create(
            name="Custom builder SKU",
            slug="gate-cb-sku",
            included_features=["reports_custom_builder"],
            is_active=True,
        )

    def test_builder_403_without_custom_builder_or_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="NCB",
            slug="gate-ncb",
            subdomain="gate-ncb",
            is_active=True,
            plan=self.plan_no_reports,
        )
        request = self.factory.get("/siteconfig/reports/builder/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_preview_path_200_with_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="PV",
            slug="gate-cb-pv",
            subdomain="gate-cb-pv",
            is_active=True,
            plan=self.plan_coarse_reports,
        )
        request = self.factory.get("/siteconfig/reports/preview/my-style/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)

    def test_adhoc_api_200_with_granular_custom_builder_only(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="ADH",
            slug="gate-cb-adh",
            subdomain="gate-cb-adh",
            is_active=True,
            plan=self.plan_custom_builder_only,
        )
        request = self.factory.get("/api/v1/reports/adhoc/42/run")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)

    def test_adhoc_api_403_returns_json_payload(self):
        import json

        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="ADH403",
            slug="gate-cb-adh403",
            subdomain="gate-cb-adh403",
            is_active=True,
            plan=self.plan_no_reports,
        )
        request = self.factory.get(
            "/api/v1/reports/adhoc",
            HTTP_ACCEPT="application/json",
        )
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        resp = mw(request)
        self.assertEqual(resp.status_code, 403)
        data = json.loads(resp.content)
        self.assertEqual(data.get("error"), "feature_not_available")

    def test_report_download_403_without_custom_builder_or_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="NDL",
            slug="gate-ndl",
            subdomain="gate-ndl",
            is_active=True,
            plan=self.plan_no_reports,
        )
        request = self.factory.get("/siteconfig/reports/download/term-style/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_bulk_letters_200_with_granular_custom_builder_only(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="BL",
            slug="gate-bl",
            subdomain="gate-bl",
            is_active=True,
            plan=self.plan_custom_builder_only,
        )
        request = self.factory.get("/siteconfig/reports/bulk-letters/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)


class ReportScheduledDeliveryFeatureGateAnyOfTests(TestCase):
    """Batch 14+: scheduled delivery hub + API list require granular or coarse reports entitlement."""

    def setUp(self):
        self.factory = RequestFactory()
        self.plan_no_reports = Plan.objects.create(
            name="Lite SD",
            slug="gate-sd-lite",
            included_features=["library"],
            is_active=True,
        )
        self.plan_coarse_reports = Plan.objects.create(
            name="Std SD",
            slug="gate-sd-std",
            included_features=["reports"],
            is_active=True,
        )
        self.plan_scheduled_only = Plan.objects.create(
            name="Scheduled SKU",
            slug="gate-sd-sku",
            included_features=["reports_scheduled_delivery"],
            is_active=True,
        )

    def test_scheduled_hub_403_without_scheduled_or_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="NSD",
            slug="gate-nsd",
            subdomain="gate-nsd",
            is_active=True,
            plan=self.plan_no_reports,
        )
        request = self.factory.get("/siteconfig/reports/scheduled/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 403)

    def test_scheduled_hub_200_with_coarse_reports(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="CRSD",
            slug="gate-crsd",
            subdomain="gate-crsd",
            is_active=True,
            plan=self.plan_coarse_reports,
        )
        request = self.factory.get("/siteconfig/reports/scheduled/")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)

    def test_scheduled_api_200_with_granular_scheduled_delivery_only(self):
        from apps.schools.middleware import FeatureGatekeeperMiddleware

        school = School.objects.create(
            name="SDONLY",
            slug="gate-sdonly",
            subdomain="gate-sdonly",
            is_active=True,
            plan=self.plan_scheduled_only,
        )
        request = self.factory.get("/api/v1/reports/scheduled")
        request.school = school
        mw = FeatureGatekeeperMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(request).status_code, 200)


class SchoolHasFeaturePhaseDTests(TestCase):
    """School.has_feature() uses is_feature_enabled (Phase D)."""

    def test_has_feature_via_plan(self):
        plan = Plan.objects.create(
            name="Pro",
            slug="pro",
            included_features=["reports", "finance"],
            is_active=True,
        )
        school = School.objects.create(
            name="Pro School",
            slug="pro-school",
            subdomain="pro-school",
            is_active=True,
            plan=plan,
        )
        self.assertTrue(school.has_feature("reports"))
        self.assertTrue(school.has_feature("finance"))
        self.assertFalse(school.has_feature("design_studio"))
