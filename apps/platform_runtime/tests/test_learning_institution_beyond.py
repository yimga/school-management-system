"""Beyond-reach wedges 23–43: feature gate, pack install, terminology, suggest, benchmarks."""

import json

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.platform_runtime.learning_institution_catalog import (
    CATALOG_VERSION,
    terminology_for_locale,
)
from apps.platform_runtime.learning_institution_runtime import (
    aggregate_learning_wedge_benchmarks,
    apply_single_wedge_pack_slug,
    suggest_institution_profile_from_school,
)
from apps.schools.models import School, is_feature_enabled


class LearningInstitutionBeyondTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Test Academy",
            slug="test-academy",
            subdomain="test-academy",
            is_active=True,
            billing_type=School.BillingType.REGULAR,
        )
        self.admin = User.objects.create_user(
            username="wedge_admin",
            email="w@t.com",
            password="x",
            role=User.Role.ADMIN,
        )

    def test_is_feature_enabled_honors_school_features_from_packs(self):
        self.school.features = {"rubrics": True}
        self.school.save()
        self.assertTrue(is_feature_enabled(self.school, "rubrics"))

    def test_apply_single_wedge_pack_enables_mapped_features(self):
        apply_single_wedge_pack_slug(self.school, "evals_rubrics")
        self.school.refresh_from_db()
        self.assertTrue(self.school.features.get("rubrics"))
        self.assertIn(
            "evals_rubrics",
            self.school.settings.get("wedge_marketplace_installs") or [],
        )

    def test_suggest_institution_heuristic_higher_ed(self):
        self.school.name = "Riverside University College"
        out = suggest_institution_profile_from_school(self.school)
        self.assertEqual(out["institution_type_code"], "W43_HIGHER_EDUCATION")
        self.assertEqual(out["catalog_version"], CATALOG_VERSION)

    def test_terminology_pack_fr(self):
        t = terminology_for_locale("fr")
        self.assertEqual(t.get("student"), "Élève")

    def test_aggregate_benchmarks_shape(self):
        out = aggregate_learning_wedge_benchmarks()
        self.assertIn("active_schools_total", out)
        self.assertEqual(out["catalog_version"], CATALOG_VERSION)

    def test_learning_pack_install_view(self):
        from apps.api.learning_institution_api import LearningPackInstallView

        rf = RequestFactory()
        req = rf.post(
            "/api/learning/pack-install/",
            data=json.dumps(
                {"pack_slug": "core_scheduling", "record_marketplace": False}
            ),
            content_type="application/json",
        )
        req.user = self.admin
        req.school = self.school
        resp = LearningPackInstallView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        self.school.refresh_from_db()
        self.assertTrue(
            self.school.features.get("timetable")
            or self.school.features.get("scheduling")
        )

    def test_institution_suggest_view(self):
        from apps.api.learning_institution_api import InstitutionProfileSuggestView

        rf = RequestFactory()
        req = rf.get("/api/learning/institution-suggest/")
        req.user = self.admin
        req.school = self.school
        resp = InstitutionProfileSuggestView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("delivery_mode_codes", data)

    def test_terminology_api(self):
        from apps.api.learning_institution_api import TerminologyPackView

        rf = RequestFactory()
        req = rf.get("/api/learning/terminology/?locale=en")
        resp = TerminologyPackView.as_view()(req)
        self.assertEqual(resp.status_code, 200)

    def test_ministry_pdf_returns_pdf(self):
        from apps.api.learning_institution_api import MinistryStubPdfView

        rf = RequestFactory()
        req = rf.get("/api/learning/ministry-pdf/?stub=stub_census_headcount")
        req.user = self.admin
        req.school = self.school
        resp = MinistryStubPdfView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content[:4] == b"%PDF")

    def test_benchmarks_superuser_only(self):
        from apps.api.learning_institution_api import LearningWedgeBenchmarksView

        rf = RequestFactory()
        su = User.objects.create_superuser(
            username="su_bench", email="su@b.com", password="x"
        )
        req = rf.get("/api/internal/learning-wedge-benchmarks/")
        req.user = su
        resp = LearningWedgeBenchmarksView.as_view()(req)
        self.assertEqual(resp.status_code, 200)

        req2 = rf.get("/api/internal/learning-wedge-benchmarks/")
        req2.user = self.admin
        with self.assertRaises(PermissionDenied):
            LearningWedgeBenchmarksView.as_view()(req2)
