"""Wave K4: data residency readiness preflight tests.

Covers:

1. Empty platform (no schools) is trivially ready.
2. A school whose regulatory region has no replica registered surfaces
   in ``missing_replicas``.
3. A school whose operational alias differs from regulatory region
   surfaces in ``misaligned_schools``.
4. A school with blank ``data_region`` whose country maps to a
   non-global derived region surfaces in ``unbackfilled_schools``.
5. With every issue resolved (replica registered + aligned + backfilled),
   the report is ``ready=True`` and the command exits 0.
6. The CLI command exits 1 when issues exist.
"""

from __future__ import annotations

import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.schools.models import School
from apps.schools.residency_readiness import assess_readiness
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig


def _make(*, country="", data_region="", regional_cluster="", plan=None, region=None):
    slug = f"k4-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"K4 {slug}", slug=slug, subdomain=slug, is_active=True,
        plan=plan, default_region=region, country_code=country,
        data_region=data_region, regional_cluster=regional_cluster,
        settings={},
    )


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ResidencyReadinessTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="K4", slug="k4-plan", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="K4", name="K4land", timezone="UTC", default_currency="USD"
        )

    def test_no_k4_schools_means_no_k4_specific_issues(self):
        # Other tests in the keepdb DB may have committed schools; we
        # only assert that no K4-namespaced misalignment / unbackfill
        # surfaces when we haven't created any K4 schools.
        with override_settings(DATA_RESIDENCY_REPLICA_ALIASES={}):
            report = assess_readiness()
        for slug, _, _ in report.misaligned_schools:
            self.assertFalse(slug.startswith("k4-"))
        for slug, _, _ in report.unbackfilled_schools:
            self.assertFalse(slug.startswith("k4-"))

    def test_missing_replica_surfaces(self):
        _make(plan=self.plan, region=self.region, country="DE", data_region="eu_central")
        with override_settings(DATA_RESIDENCY_REPLICA_ALIASES={}):
            report = assess_readiness()
        self.assertFalse(report.ready)
        self.assertIn("eu_central", report.missing_replicas)

    def test_replica_present_clears_missing(self):
        _make(plan=self.plan, region=self.region, country="DE", data_region="eu_central",
              regional_cluster="eu_central")
        with override_settings(
            DATA_RESIDENCY_REPLICA_ALIASES={"eu_central": "replica_eu_central"},
        ):
            report = assess_readiness()
        self.assertEqual(report.missing_replicas, [])

    def test_misaligned_tenant_surfaces(self):
        _make(plan=self.plan, region=self.region, country="DE", data_region="eu_central",
              regional_cluster="us_east")
        with override_settings(
            DATA_RESIDENCY_REPLICA_ALIASES={
                "eu_central": "replica_eu_central",
                "us_east": "replica_us_east",
            },
        ):
            report = assess_readiness()
        self.assertFalse(report.ready)
        self.assertEqual(len(report.misaligned_schools), 1)
        slug, regulatory, operational = report.misaligned_schools[0]
        self.assertEqual(regulatory, "eu_central")
        self.assertEqual(operational, "us_east")

    def test_unbackfilled_tenant_surfaces(self):
        # German tenant with NO data_region set — derive will be eu_central.
        _make(plan=self.plan, region=self.region, country="DE", data_region="",
              regional_cluster="")
        report = assess_readiness()
        self.assertFalse(report.ready)
        self.assertTrue(any(row[0].startswith("k4-") for row in report.unbackfilled_schools))

    def test_global_country_does_not_require_backfill(self):
        # Empty country → derived "global" → does NOT surface as unbackfilled.
        _make(plan=self.plan, region=self.region, country="", data_region="",
              regional_cluster="")
        report = assess_readiness()
        self.assertEqual(report.unbackfilled_schools, [])

    def test_global_region_does_not_require_replica(self):
        _make(plan=self.plan, region=self.region, country="", data_region="global",
              regional_cluster="")
        with override_settings(DATA_RESIDENCY_REPLICA_ALIASES={}):
            report = assess_readiness()
        # 'global' must not appear in missing_replicas — it's served by default.
        self.assertNotIn("global", report.missing_replicas)

    def test_fully_aligned_is_ready(self):
        _make(plan=self.plan, region=self.region, country="DE", data_region="eu_central",
              regional_cluster="eu_central")
        _make(plan=self.plan, region=self.region, country="GB", data_region="uk",
              regional_cluster="uk")
        with override_settings(
            DATA_RESIDENCY_REPLICA_ALIASES={
                "eu_central": "replica_eu_central",
                "uk": "replica_uk",
            },
        ):
            report = assess_readiness()
        self.assertTrue(
            report.ready,
            msg=(
                f"expected ready, got: missing={report.missing_replicas}, "
                f"misaligned={report.misaligned_schools}, "
                f"unbackfilled={report.unbackfilled_schools}"
            ),
        )

    def test_school_slug_filter_narrows_audit(self):
        a = _make(plan=self.plan, region=self.region, country="DE", data_region="eu_central",
                  regional_cluster="us_east")  # misaligned
        b = _make(plan=self.plan, region=self.region, country="GB", data_region="uk",
                  regional_cluster="uk")  # aligned
        with override_settings(
            DATA_RESIDENCY_REPLICA_ALIASES={
                "eu_central": "replica_eu_central",
                "us_east": "replica_us_east",
                "uk": "replica_uk",
            },
        ):
            report_a = assess_readiness(slug_filter=a.slug)
            report_b = assess_readiness(slug_filter=b.slug)
        self.assertFalse(report_a.ready)  # the misaligned one
        self.assertTrue(report_b.ready)  # the aligned one

    def test_command_exits_1_when_not_ready(self):
        _make(plan=self.plan, region=self.region, country="DE", data_region="eu_central")
        with self.assertRaises(SystemExit) as cm:
            with override_settings(DATA_RESIDENCY_REPLICA_ALIASES={}):
                call_command("verify_residency_readiness", "--quiet", stdout=StringIO())
        self.assertEqual(cm.exception.code, 1)

    def test_command_exits_0_when_ready(self):
        _make(plan=self.plan, region=self.region, country="DE", data_region="eu_central",
              regional_cluster="eu_central")
        out = StringIO()
        with override_settings(
            DATA_RESIDENCY_REPLICA_ALIASES={"eu_central": "replica_eu_central"},
        ):
            # No SystemExit raised → exit 0.
            call_command("verify_residency_readiness", stdout=out)
        self.assertIn("READY", out.getvalue())
