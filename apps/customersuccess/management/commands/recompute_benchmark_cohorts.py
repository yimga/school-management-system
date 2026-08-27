"""Producer for peer-benchmark cohorts + privacy-safe aggregates.

Closes the long-standing read-without-writer gap: ``BenchmarkCohort`` /
``BenchmarkCohortMetric`` rows are CONSUMED by the operator peer-benchmarking
dashboard + ``apps.customersuccess.services`` but nothing produced them, so the
surface always rendered empty.

This command:
  1. Buckets active schools by (country_code, size_band, institution_type)
     derived from the public School registry (+ a best-effort per-tenant student
     count for the size band; degrades to "unknown" when the tenant schema isn't
     reachable from here).
  2. Creates/refreshes an auto ``BenchmarkCohort`` per bucket that clears the
     k-anonymity floor (``--min-members`` / ``BENCHMARK_COHORT_MIN_MEMBERS``,
     default 5); deactivates auto-cohorts that fall below it.
  3. Computes per-cohort ``BenchmarkCohortMetric`` percentiles (p25/p50/p75/avg)
     from the latest TenantMaturityScore + TenantHealthScore of member schools,
     publishing a metric ONLY when >= K schools contributed a value
     (small-cell suppression). No individual tenant's figure is recoverable.

Idempotent: safe to re-run (and to schedule via Celery beat). Read-only with
``--dry-run``.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

# Re-exported so callers keep a stable name; the value and the env override now
# live in services, where the READ path can apply the identical floor.
from apps.customersuccess.services import (  # noqa: E402
    DEFAULT_BENCHMARK_MIN_MEMBERS as DEFAULT_MIN_MEMBERS,
)


def _resolve_min_members(explicit: int | None) -> int:
    """Delegates to services so the READER can apply an identical floor."""
    from apps.customersuccess.services import resolve_benchmark_min_members

    return resolve_benchmark_min_members(explicit)


def _student_count(school) -> int | None:
    """Best-effort student count for the size band.

    Thin alias for ``services.student_count_for_size_band`` -- producer and
    reader must derive the band from the SAME function, or an unreadable count
    buckets one way here and another way in ``match_active_cohort`` and the
    cohort this command publishes can never be matched back.
    """
    from apps.customersuccess.services import student_count_for_size_band

    return student_count_for_size_band(school)


def _percentile(sorted_vals: list[float], q: float) -> Decimal:
    """Linear-interpolation percentile (q in 0..1). Assumes sorted_vals non-empty."""
    if len(sorted_vals) == 1:
        return Decimal(str(round(sorted_vals[0], 2)))
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    val = sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac
    return Decimal(str(round(val, 2)))


class Command(BaseCommand):
    help = "Produce peer-benchmark cohorts + k-anonymous aggregate metrics."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Compute + report, do not write.")
        parser.add_argument("--min-members", type=int, default=0, help="k-anonymity floor (default env or 5).")

    def handle(self, *args, **options):
        from apps.customersuccess.services import size_band_for_count
        from apps.schools.models import School

        k = _resolve_min_members(options.get("min_members"))
        dry = bool(options.get("dry_run"))
        now = timezone.now()

        # 1. Bucket active schools.
        buckets: dict[tuple[str, str, str], list] = {}
        # tenant-isolation-allow: cross-tenant operator analytics over the public school registry
        for school in School.objects.filter(is_active=True).only(
            "id", "country_code", "school_type"
        ):
            country = (getattr(school, "country_code", "") or "").strip().upper()
            inst = (getattr(school, "school_type", "") or "").strip().lower()
            band = size_band_for_count(_student_count(school))
            key = (country, band, inst)
            buckets.setdefault(key, []).append(school)

        eligible = {key: members for key, members in buckets.items() if len(members) >= k}
        self.stdout.write(
            f"buckets={len(buckets)} eligible(>= {k})={len(eligible)} (dry_run={dry})"
        )

        if dry:
            for (country, band, inst), members in sorted(eligible.items()):
                self.stdout.write(f"  cohort[{country}/{band}/{inst}] members={len(members)}")
            self._report_metric_preview(eligible, k)
            return

        produced, deactivated, metrics_written = self._apply(eligible, buckets, k, now)
        self.stdout.write(self.style.SUCCESS(
            f"cohorts produced/active={produced} deactivated={deactivated} metrics={metrics_written}"
        ))

    # ----- write path ------------------------------------------------------

    def _apply(self, eligible, buckets, k, now):
        from apps.customersuccess.models import BenchmarkCohort

        produced = 0
        active_keys = set()
        for (country, band, inst), members in eligible.items():
            cohort, _created = BenchmarkCohort.objects.get_or_create(
                country_code=country, size_band=band, institution_type=inst, is_auto=True,
                defaults={"name": self._cohort_name(country, band, inst)},
            )
            cohort.name = self._cohort_name(country, band, inst)
            cohort.member_count = len(members)
            cohort.is_active = True
            cohort.last_computed_at = now
            cohort.save(update_fields=["name", "member_count", "is_active", "last_computed_at", "updated_at"])
            active_keys.add((country, band, inst))
            produced += 1
            self._write_cohort_metrics(cohort, members, k, now)

        # Deactivate auto-cohorts that no longer clear the floor.
        deactivated = 0
        for cohort in BenchmarkCohort.objects.filter(is_auto=True, is_active=True):
            key = (cohort.country_code, cohort.size_band, cohort.institution_type)
            if key not in active_keys:
                cohort.is_active = False
                cohort.member_count = len(buckets.get(key, []))
                cohort.last_computed_at = now
                cohort.save(update_fields=["is_active", "member_count", "last_computed_at", "updated_at"])
                # Suppress now-stale published metrics.
                cohort.metrics.all().delete()
                deactivated += 1

        metrics_written = sum(
            c.metrics.count() for c in BenchmarkCohort.objects.filter(is_auto=True, is_active=True)
        )
        return produced, deactivated, metrics_written

    def _write_cohort_metrics(self, cohort, members, k, now):
        from apps.customersuccess.models import BenchmarkCohortMetric

        series = self._collect_series(members)
        seen_keys = set()
        for metric_key, values in series.items():
            if len(values) < k:
                # Small-cell suppression — drop any prior published value too.
                BenchmarkCohortMetric.objects.filter(cohort=cohort, metric_key=metric_key).delete()
                continue
            vals = sorted(float(v) for v in values)
            BenchmarkCohortMetric.objects.update_or_create(
                cohort=cohort, metric_key=metric_key,
                defaults={
                    "member_count": len(vals),
                    "p25": _percentile(vals, 0.25),
                    "p50": _percentile(vals, 0.50),
                    "p75": _percentile(vals, 0.75),
                    "avg": Decimal(str(round(sum(vals) / len(vals), 2))),
                    "computed_at": now,
                },
            )
            seen_keys.add(metric_key)
        # Remove metric keys that no longer have data.
        cohort.metrics.exclude(metric_key__in=seen_keys).delete()

    # ----- data collection -------------------------------------------------

    def _collect_series(self, members) -> dict[str, list[float]]:
        """Latest maturity (overall + per-dimension) and health value per member."""
        from apps.customersuccess.models import TenantHealthScore, TenantMaturityScore

        member_ids = [m.pk for m in members]
        series: dict[str, list[float]] = {}

        # Latest health score per school.
        health_latest: dict[int, float] = {}
        # tenant-isolation-allow: cross-tenant operator aggregate keyed by school id
        for row in TenantHealthScore.objects.filter(school_id__in=member_ids).order_by(
            "school_id", "-computed_at"
        ).values("school_id", "score"):
            health_latest.setdefault(row["school_id"], float(row["score"]))
        if health_latest:
            series["health:overall"] = list(health_latest.values())

        # Latest maturity score per (school, dimension).
        mat_latest: dict[tuple[int, str], float] = {}
        # tenant-isolation-allow: cross-tenant operator aggregate keyed by school id
        for row in TenantMaturityScore.objects.filter(school_id__in=member_ids).order_by(
            "school_id", "dimension", "-computed_at"
        ).values("school_id", "dimension", "score"):
            key = (row["school_id"], row["dimension"])
            mat_latest.setdefault(key, float(row["score"]))
        # Per-dimension series + an overall (mean of a school's dimensions).
        per_school_scores: dict[int, list[float]] = {}
        for (school_id, dimension), score in mat_latest.items():
            series.setdefault(f"maturity:{dimension}", []).append(score)
            per_school_scores.setdefault(school_id, []).append(score)
        if per_school_scores:
            series["maturity:overall"] = [
                sum(v) / len(v) for v in per_school_scores.values() if v
            ]
        return series

    def _report_metric_preview(self, eligible, k):
        for (country, band, inst), members in sorted(eligible.items()):
            series = self._collect_series(members)
            publishable = {key: len(v) for key, v in series.items() if len(v) >= k}
            if publishable:
                self.stdout.write(f"  metrics[{country}/{band}/{inst}]: {publishable}")

    @staticmethod
    def _cohort_name(country: str, band: str, inst: str) -> str:
        parts = [p for p in (inst.title() or "", band.title() or "", country or "Global") if p]
        return " · ".join(parts) or "Global cohort"
