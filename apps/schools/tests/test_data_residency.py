"""Wave E — G4: data residency derivation + alignment tests."""

from __future__ import annotations

import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.platform_runtime.models import RuntimeDefaults
from apps.schools.data_residency import (
    CANONICAL_REGIONS,
    CrossRegionWriteError,
    assert_aligned_or_log,
    derive_default_region,
    effective_region,
    is_aligned,
    is_canonical,
)
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig


def _make(country="", data_region="", regional_cluster="", plan=None, region=None):
    slug = f"res-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"Residency {slug}", slug=slug, subdomain=slug, is_active=True,
        plan=plan, default_region=region, country_code=country,
        data_region=data_region, regional_cluster=regional_cluster,
        settings={},
    )


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class DataResidencyTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Res", slug="res", included_features=["core"], is_active=True)
        cls.region = RegionConfig.objects.create(code="RS", name="Rsland", timezone="UTC", default_currency="USD")

    def setUp(self):
        RuntimeDefaults.objects.all().delete()

    def test_canonical_regions_include_expected(self):
        for code in ("eu_central", "us_east", "uk", "apac_southeast", "afr_west", "global"):
            self.assertIn(code, CANONICAL_REGIONS)

    def test_derive_known_country_codes(self):
        self.assertEqual(derive_default_region("DE"), "eu_central")
        self.assertEqual(derive_default_region("US"), "us_east")
        self.assertEqual(derive_default_region("GB"), "uk")
        self.assertEqual(derive_default_region("SG"), "apac_southeast")

    def test_derive_unknown_country_falls_back_to_global(self):
        self.assertEqual(derive_default_region(""), "global")
        self.assertEqual(derive_default_region("ZZ"), "global")

    def test_country_override_via_runtime_defaults(self):
        RuntimeDefaults.objects.create(
            payload={"data_residency.country_overrides": {"DE": "eu_west"}}
        )
        self.assertEqual(derive_default_region("DE"), "eu_west")

    def test_effective_region_prefers_explicit_data_region(self):
        school = _make(country="DE", data_region="us_east", plan=self.plan, region=self.region)
        self.assertEqual(effective_region(school), "us_east")

    def test_effective_region_derives_when_blank(self):
        school = _make(country="FR", plan=self.plan, region=self.region)
        self.assertEqual(effective_region(school), "eu_central")

    def test_is_canonical(self):
        self.assertTrue(is_canonical("eu_central"))
        self.assertFalse(is_canonical("mars_orbital"))

    def test_is_aligned_when_clusters_match(self):
        school = _make(country="DE", regional_cluster="eu_central", plan=self.plan, region=self.region)
        self.assertTrue(is_aligned(school))

    def test_is_aligned_blank_operational_treated_as_aligned(self):
        school = _make(country="DE", regional_cluster="", plan=self.plan, region=self.region)
        self.assertTrue(is_aligned(school))

    def test_is_misaligned_when_clusters_disagree(self):
        school = _make(country="DE", regional_cluster="us_east", plan=self.plan, region=self.region)
        self.assertFalse(is_aligned(school))

    def test_assert_aligned_or_log_soft_logs(self):
        school = _make(country="DE", regional_cluster="us_east", plan=self.plan, region=self.region)
        # Default settings: DATA_RESIDENCY_ENFORCE absent / False -> no raise
        assert_aligned_or_log(school)

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    def test_assert_aligned_or_log_raises_in_strict_mode(self):
        school = _make(country="DE", regional_cluster="us_east", plan=self.plan, region=self.region)
        with self.assertRaises(CrossRegionWriteError):
            assert_aligned_or_log(school)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class VerifyDataResidencyCommandTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="ResCmd", slug="rescmd", included_features=["core"], is_active=True)
        cls.region = RegionConfig.objects.create(code="RC", name="RCland", timezone="UTC", default_currency="USD")

    def test_verify_reports_misalignment(self):
        _make(country="DE", regional_cluster="us_east", plan=self.plan, region=self.region)
        out = StringIO()
        call_command("verify_data_residency", stdout=out)
        body = out.getvalue()
        self.assertIn("misaligned", body)
        self.assertIn("regulatory=eu_central", body)

    def test_fix_derive_backfills_data_region(self):
        school = _make(country="DE", plan=self.plan, region=self.region)
        self.assertEqual(school.data_region, "")
        out = StringIO()
        call_command("verify_data_residency", "--fix-derive", stdout=out)
        school.refresh_from_db()
        self.assertEqual(school.data_region, "eu_central")

    def test_strict_exits_nonzero_when_misaligned(self):
        _make(country="DE", regional_cluster="us_east", plan=self.plan, region=self.region)
        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("verify_data_residency", "--strict", stdout=out)
        self.assertEqual(ctx.exception.code, 1)
