"""
Predictive Engine (StudentSignals): nightly risk scoring.
Computes at-risk score per student per school and persists to RiskFactor.
Run via cron or Celery Beat (e.g. daily). Uses AdvancedAnalyticsService.identify_at_risk_students
and optional ML predictors for score + reason_summary.
"""

from django.core.management.base import BaseCommand
from django.db import DatabaseError, OperationalError
from django.utils import timezone

from apps.analytics.models import RiskFactor
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.schools.models import School

# Typed exceptions for nightly risk inference (import, DB, service); §2.4 broad-except policy.
_COMPUTE_NIGHTLY_RISK_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
    OperationalError,
)


class Command(BaseCommand):
    help = "Compute and persist nightly risk scores (StudentSignals / Predictive Engine)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            type=str,
            help="School ID (UUID) to process; omit to process all active schools.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print what would be written, do not save.",
        )

    def handle(self, *args, **options):
        school_id = options.get("school")
        dry_run = options.get("dry_run", False)
        schools = School.objects.filter(is_active=True)
        if school_id:
            schools = schools.filter(id=school_id)
        if not schools.exists():
            self.stdout.write("No schools to process.")
            return
        total = 0
        for school in schools:
            n = self._process_school(school, dry_run)
            total += n
        self.stdout.write(self.style.SUCCESS(f"Wrote {total} risk factor(s)."))

    def _process_school(self, school, dry_run):
        try:
            from apps.analytics.ml_inference import run_risk_inference_batch
            results = run_risk_inference_batch(school_id=str(school.id), threshold=50)
        except _COMPUTE_NIGHTLY_RISK_ERRORS as e:
            log_exception_with_context(
                "compute_nightly_risk: school batch failed",
                school_id=str(school.id),
                extra={"command": "compute_nightly_risk", "error": str(e)},
            )
            self.stderr.write(self.style.ERROR(f"School {school.id}: {e}"))
            return 0
        count = 0
        for student, score, reason, model_version in results:
            if dry_run:
                self.stdout.write(
                    f"  Would write RiskFactor: school={school.id} student={student.id} score={score} model={model_version or 'default'}"
                )
                count += 1
                continue
            RiskFactor.objects.update_or_create(
                school=school,
                student=student,
                defaults={
                    "score": score,
                    "reason_summary": reason,
                    "model_version": model_version or "",
                    "computed_at": timezone.now(),
                },
            )
            count += 1
        return count
