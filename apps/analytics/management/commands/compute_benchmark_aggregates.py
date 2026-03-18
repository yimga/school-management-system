"""
ETL: compute anonymized benchmark aggregates per region/sub_system from Evaluation data (Phase 4).
No PII; run periodically (e.g. cron). Creates/updates BenchmarkAggregate rows.
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Avg, Count

from apps.analytics.models import BenchmarkAggregate
from apps.evals.models import Evaluation


class Command(BaseCommand):
    help = "Compute anonymized benchmark aggregates (region/sub_system/subject/term) for AI benchmarking."

    def add_arguments(self, parser):
        parser.add_argument(
            "--region", type=str, default="", help="Limit to region code (e.g. CMR)."
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Only print, do not save."
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        region_filter = (options["region"] or "").strip()
        # Get evaluations with school -> default_region and sub_system (from school)
        from apps.schools.models import School

        # Aggregate by school's region_code (from default_region) and sub_system, then by subject/term
        schools = School.objects.filter(is_active=True).select_related("default_region")
        if region_filter:
            schools = schools.filter(default_region__code=region_filter)
        created = 0
        for school in schools:
            region_code = (
                getattr(school.default_region, "code", None)
                if school.default_region
                else "GLOBAL"
            )
            sub_system = getattr(school, "sub_system", "EN") or "EN"
            # Evaluations for this school (tenant-scoped)
            evals = (
                Evaluation.objects.filter(
                    subject_assignment__school=school,
                )
                .values(
                    "subject_assignment__subject_id",
                    "subject_assignment__term_id",
                    "subject_assignment__academic_year_id",
                )
                .annotate(
                    avg_score=Avg("final_score"),
                    n=Count("id"),
                )
            )
            for row in evals:
                subject_id = row.get("subject_assignment__subject_id")
                term_id = row.get("subject_assignment__term_id")
                ay_id = row.get("subject_assignment__academic_year_id")
                avg_score = row.get("avg_score")
                n = row.get("n") or 0
                if avg_score is None or n == 0:
                    continue
                if dry_run:
                    self.stdout.write(
                        f"Would create: {region_code}/{sub_system} subject={subject_id} term={term_id} average_score={avg_score} n={n}"
                    )
                    continue
                obj, created_flag = BenchmarkAggregate.objects.update_or_create(
                    region_code=region_code,
                    sub_system=sub_system,
                    subject_id=subject_id,
                    term_id=term_id,
                    academic_year_id=ay_id,
                    metric="average_score",
                    defaults={"value": Decimal(str(avg_score)), "sample_size": n},
                )
                if created_flag:
                    created += 1
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Benchmark aggregates updated. New rows: {created}."
                )
            )
        else:
            self.stdout.write("Dry run complete.")
