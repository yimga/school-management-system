"""
Phase D: Tests for Plan model, is_feature_enabled (plan + addons), and Feature Gatekeeper middleware.
"""

from django.test import TestCase, RequestFactory
from django.http import HttpResponse

from apps.schools.models import School, is_feature_enabled
from apps.siteconfig.models import Plan


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
