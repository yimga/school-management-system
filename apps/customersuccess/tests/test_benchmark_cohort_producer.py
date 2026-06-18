"""Seal: the benchmark cohort producer closes the read-without-writer gap and
respects the k-anonymity floor + small-cell suppression."""
from __future__ import annotations

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.customersuccess.models import (
    BenchmarkCohort,
    BenchmarkCohortMetric,
    TenantHealthScore,
    TenantMaturityScore,
)
from apps.schools.models import School


def _school(slug, country="NG", school_type="private"):
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug,
        country_code=country, school_type=school_type, is_active=True,
    )


class BenchmarkCohortProducerTests(TestCase):
    def test_cohort_and_metrics_produced_above_floor(self):
        a = _school("alpha-ng")
        b = _school("beta-ng")
        TenantMaturityScore.objects.create(school=a, dimension="finance", score=Decimal("40"))
        TenantMaturityScore.objects.create(school=b, dimension="finance", score=Decimal("60"))
        TenantHealthScore.objects.create(school=a, score=Decimal("70"))
        TenantHealthScore.objects.create(school=b, score=Decimal("90"))

        call_command("recompute_benchmark_cohorts", min_members=2)

        cohort = BenchmarkCohort.objects.get(
            is_auto=True, country_code="NG", size_band="micro", institution_type="private"
        )
        self.assertTrue(cohort.is_active)
        self.assertEqual(cohort.member_count, 2)

        overall = BenchmarkCohortMetric.objects.get(cohort=cohort, metric_key="maturity:overall")
        self.assertEqual(overall.member_count, 2)
        self.assertEqual(float(overall.p50), 50.0)
        health = BenchmarkCohortMetric.objects.get(cohort=cohort, metric_key="health:overall")
        self.assertEqual(float(health.p50), 80.0)

    def test_below_floor_yields_no_cohort(self):
        _school("solo-ke", country="KE")
        TenantHealthScore.objects.get_or_create(
            school=School.objects.get(slug="solo-ke"), defaults={"score": Decimal("50")}
        )
        call_command("recompute_benchmark_cohorts", min_members=2)
        self.assertFalse(
            BenchmarkCohort.objects.filter(is_auto=True, is_active=True, country_code="KE").exists()
        )

    def test_small_cell_suppression_per_metric(self):
        a = _school("alpha2-ng")
        b = _school("beta2-ng")
        # Both contribute maturity (>= floor) ...
        TenantMaturityScore.objects.create(school=a, dimension="finance", score=Decimal("30"))
        TenantMaturityScore.objects.create(school=b, dimension="finance", score=Decimal("50"))
        # ... but only ONE contributes a health score (< floor of 2).
        TenantHealthScore.objects.create(school=a, score=Decimal("88"))

        call_command("recompute_benchmark_cohorts", min_members=2)
        cohort = BenchmarkCohort.objects.get(is_auto=True, country_code="NG", institution_type="private")
        self.assertTrue(
            BenchmarkCohortMetric.objects.filter(cohort=cohort, metric_key="maturity:overall").exists()
        )
        # Health has only 1 contributor → suppressed.
        self.assertFalse(
            BenchmarkCohortMetric.objects.filter(cohort=cohort, metric_key="health:overall").exists()
        )

    def test_idempotent_rerun(self):
        _school("a-id")
        _school("b-id")
        call_command("recompute_benchmark_cohorts", min_members=2)
        call_command("recompute_benchmark_cohorts", min_members=2)
        self.assertEqual(
            BenchmarkCohort.objects.filter(
                is_auto=True, country_code="NG", size_band="micro", institution_type="private"
            ).count(),
            1,
        )

    def test_falling_below_floor_deactivates_and_suppresses(self):
        a = _school("x-ng")
        b = _school("y-ng")
        TenantMaturityScore.objects.create(school=a, dimension="ops", score=Decimal("40"))
        TenantMaturityScore.objects.create(school=b, dimension="ops", score=Decimal("60"))
        call_command("recompute_benchmark_cohorts", min_members=2)
        cohort = BenchmarkCohort.objects.get(is_auto=True, country_code="NG")
        self.assertTrue(cohort.is_active)

        # Raise the floor so the bucket (2 members) no longer qualifies.
        call_command("recompute_benchmark_cohorts", min_members=5)
        cohort.refresh_from_db()
        self.assertFalse(cohort.is_active)
        self.assertEqual(cohort.metrics.count(), 0)
