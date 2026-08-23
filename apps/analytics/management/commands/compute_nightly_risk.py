"""
Predictive Engine (StudentSignals): nightly risk scoring.
Computes at-risk score per student per school and persists to RiskFactor.
Run via cron or Celery Beat (e.g. daily). Uses AdvancedAnalyticsService.identify_at_risk_students
and optional ML predictors for score + reason_summary.
"""

from django.core.management.base import BaseCommand
from django.db import DatabaseError, OperationalError
from django.utils import timezone

from apps.analytics.models import (
    AtRiskInferenceRun,
    AtRiskModelArtifact,
    RiskFactor,
)
from apps.analytics.tenant_batch import run_for_school
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.schools.models import School

_RED_BAND_MIN = 80
_AMBER_BAND_MIN = 50

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
    help = (
        "Compute and persist nightly risk scores (StudentSignals / Predictive Engine)."
    )

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
            # AtRiskInferenceRun / RiskFactor / StudentProfile are TENANT_APPS
            # tables; without this the connection sits on `public` and the
            # nightly run reports success having written nothing.
            total += run_for_school(
                school,
                lambda school=school: self._process_school(school, dry_run),
                label="compute_nightly_risk",
                default=0,
            )
        self.stdout.write(self.style.SUCCESS(f"Wrote {total} risk factor(s)."))

    def _process_school(self, school, dry_run):
        run = None
        try:
            # Opening the run row is itself a tenant-table write. Inside the try
            # so a failure records/skips this school instead of aborting the
            # whole batch on the first one.
            if not dry_run:
                run = AtRiskInferenceRun.objects.create(
                    school=school,
                    artifact=AtRiskModelArtifact.current_production(),
                )
            from apps.analytics.ml_inference import run_risk_inference_batch

            results = run_risk_inference_batch(school_id=str(school.id), threshold=50)
        except _COMPUTE_NIGHTLY_RISK_ERRORS as e:
            log_exception_with_context(
                "compute_nightly_risk: school batch failed",
                school_id=str(school.id),
                extra={"command": "compute_nightly_risk", "error": str(e)},
            )
            self.stderr.write(self.style.ERROR(f"School {school.id}: {e}"))
            if run is not None:
                run.outcome = AtRiskInferenceRun.Outcome.FAILED
                run.error_summary = str(e)[:5000]
                run.finished_at = timezone.now()
                run.save(update_fields=["outcome", "error_summary", "finished_at"])
            return 0

        # Pass 13: entitlement gate — only run LLM-explained reasons for tenants
        # that opted in to AI features. Otherwise the canned heuristic text is fine.
        ai_explain_enabled = _is_ai_risk_explain_enabled(school)

        count = 0
        scores_for_summary: list[float] = []
        observed_version = ""
        red = amber = green = 0
        for student, score, reason, model_version in results:
            if dry_run:
                self.stdout.write(
                    f"  Would write RiskFactor: school={school.id} student={student.id} score={score} model={model_version or 'default'}"
                )
                count += 1
                continue
            final_reason = reason
            if ai_explain_enabled:
                final_reason = _llm_explained_reason(
                    school=school, student=student, score=score, reason=reason
                )
            # Wave 3: capture per-prediction model feature contributions so
            # the portal "Why" column can show top drivers instead of the
            # canned heuristic line. Cheap when model exposes
            # feature_importances_; returns [] for heuristic path.
            contributions: list[dict] = []
            try:
                from apps.analytics.ml.at_risk_model import (
                    _load_model, explain_score,
                )
                from apps.analytics.ml.at_risk_features import extract_features

                ml_model = _load_model()
                if ml_model is not None:
                    contributions = explain_score(
                        ml_model, extract_features(student)
                    )
            except _COMPUTE_NIGHTLY_RISK_ERRORS:
                # Never fail the batch on an explainability error.
                contributions = []
            risk_row, _ = RiskFactor.objects.update_or_create(
                school=school,
                student=student,
                defaults={
                    "score": score,
                    "reason_summary": final_reason,
                    "model_version": model_version or "",
                    "feature_contributions": contributions,
                    "computed_at": timezone.now(),
                },
            )
            # Derived-value lineage (2026-07-02): the score aggregates
            # per-student feature windows without materializing input PKs,
            # so lineage records the queryset scopes it actually read.
            try:
                from apps.analytics.ml.at_risk_features import DEFAULT_WINDOW_DAYS
                from apps.metadata.models_derived_lineage import (
                    record_derived_lineage,
                    risk_scope_inputs,
                )

                record_derived_lineage(
                    output=risk_row,
                    computation="analytics.nightly_risk",
                    granularity="scope",
                    version=model_version or "heuristic",
                    inputs=risk_scope_inputs(
                        student.pk, DEFAULT_WINDOW_DAYS, model_version or ""
                    ),
                )
            except Exception:  # noqa: BLE001 — lineage must never fail the batch
                pass
            count += 1
            s = float(score)
            scores_for_summary.append(s)
            if s >= _RED_BAND_MIN:
                red += 1
            elif s >= _AMBER_BAND_MIN:
                amber += 1
            else:
                green += 1
            if model_version and not observed_version:
                observed_version = str(model_version)
        if run is not None:
            mean = sum(scores_for_summary) / len(scores_for_summary) if scores_for_summary else None
            median = p95 = None
            if scores_for_summary:
                ordered = sorted(scores_for_summary)
                mid = len(ordered) // 2
                median = (
                    ordered[mid]
                    if len(ordered) % 2
                    else (ordered[mid - 1] + ordered[mid]) / 2
                )
                p95_index = max(0, int(round(0.95 * (len(ordered) - 1))))
                p95 = ordered[p95_index]
            outcome = AtRiskInferenceRun.Outcome.OK
            if not observed_version:
                outcome = AtRiskInferenceRun.Outcome.HEURISTIC_FALLBACK
            run.outcome = outcome
            run.students_scored = count
            run.students_red_band = red
            run.students_amber_band = amber
            run.students_green_band = green
            run.mean_score = mean
            run.median_score = median
            run.p95_score = p95
            run.model_version_snapshot = observed_version
            run.finished_at = timezone.now()
            run.save(update_fields=[
                "outcome", "students_scored",
                "students_red_band", "students_amber_band", "students_green_band",
                "mean_score", "median_score", "p95_score",
                "model_version_snapshot", "finished_at",
            ])
        return count


def _is_ai_risk_explain_enabled(school) -> bool:
    """
    Pass 13: gated on tenant entitlement so only opted-in schools incur the
    Anthropic API spend. Falls back to False on any error.
    """
    try:
        from apps.billing.entitlements import can

        return bool(can(school, "AI_RISK_EXPLAIN"))
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def _llm_explained_reason(*, school, student, score, reason: str) -> str:
    """
    Pass 13: returns an LLM-generated 1-2 sentence reason when available; falls
    back to the heuristic `reason` string on any failure. Never raises.
    """
    try:
        from services.risk_explanation import explain_risk

        explanation, _meta = explain_risk(
            school=school,
            student=student,
            score=float(score),
            heuristic_reason=reason,
        )
        return explanation or reason
    except _COMPUTE_NIGHTLY_RISK_ERRORS:
        log_exception_with_context(
            "compute_nightly_risk: llm explain failed",
            school_id=str(getattr(school, "id", "")),
            extra={"student_id": str(getattr(student, "id", ""))},
        )
        return reason
    except Exception:  # noqa: BLE001 - nightly batch must never fail on AI error
        return reason
