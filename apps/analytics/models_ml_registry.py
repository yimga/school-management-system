"""ML model registry — at-risk prediction artifacts and inference batches.

These two models are the *single source of truth* for which artifact is live
in production, what its measured holdout quality is, and how each nightly
inference run performed. The legacy `AT_RISK_MODEL_PATH` env-var read in
`apps.analytics.ml.at_risk_model._load_model` is now a fallback — the
registry's `is_production=True` row wins when both are present.

Lifecycle:
    1. Train produces a joblib bundle on disk.
    2. `register_at_risk_artifact` writes an `AtRiskModelArtifact` row with
       holdout metrics and status='candidate'.
    3. Operator reviews drift / shadow-comparison evidence (Wave 2).
    4. `promote_at_risk_artifact` flips status='production' atomically —
       any prior production row is moved to 'archived'.
    5. Loader resolves the active artifact via `current_production()`.

Why split from `models.py`: the existing module is ~600 LOC and growing;
this keeps the registry self-contained and easier to evolve as more model
families (grade prediction, engagement, etc.) plug into the same pattern.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class AtRiskModelArtifact(models.Model):
    """One row per trained-and-registered at-risk model artifact.

    A row is *not* automatically created by training; the operator (or the
    `retrain_at_risk_pipeline` orchestrator) explicitly registers an
    artifact after evaluation passes its gates. This means the registry
    only ever contains artifacts an operator chose to take seriously.
    """

    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Candidate (registered, not in use)"
        PRODUCTION = "production", "Production (live)"
        ARCHIVED = "archived", "Archived (previously production)"
        REJECTED = "rejected", "Rejected (failed review)"

    model_version = models.CharField(
        max_length=120,
        unique=True,
        help_text="Stable identifier — e.g. 'at_risk_v2_2026_q1' or commit-tagged.",
    )
    artifact_path = models.CharField(
        max_length=512,
        help_text="Filesystem path of the joblib bundle this row represents.",
    )
    trained_at = models.DateTimeField(
        help_text="Wall-clock time the trainer wrote the joblib bundle.",
    )
    training_dataset_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of the CSV used to train; lets us spot 'same data, "
        "different artifact' situations.",
    )
    training_row_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of labelled rows the trainer consumed.",
    )
    feature_order = models.JSONField(
        default=list,
        help_text="Snapshot of the feature list at training time. Loader "
        "compares to current feature contract to catch silent drift.",
    )

    # Holdout metrics captured by `evaluate_at_risk_model` before registration.
    metric_roc_auc = models.FloatField(null=True, blank=True)
    metric_average_precision = models.FloatField(null=True, blank=True)
    metric_ece = models.FloatField(
        null=True, blank=True,
        help_text="Expected Calibration Error from check_at_risk_calibration.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CANDIDATE,
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="at_risk_artifacts_registered",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    promoted_at = models.DateTimeField(null=True, blank=True)
    promoted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="at_risk_artifacts_promoted",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        app_label = "analytics"
        ordering = ["-registered_at"]
        indexes = [
            models.Index(fields=["status", "-registered_at"]),
            models.Index(fields=["model_version"]),
        ]
        verbose_name = "At-risk model artifact"
        verbose_name_plural = "At-risk model artifacts"

    def __str__(self) -> str:
        return f"{self.model_version} [{self.status}]"

    @classmethod
    def current_production(cls) -> "AtRiskModelArtifact | None":
        """Return the artifact the loader should serve, or None if no row is live."""
        return cls.objects.filter(status=cls.Status.PRODUCTION).order_by(
            "-promoted_at"
        ).first()

    @transaction.atomic
    def promote(self, *, by_user) -> "AtRiskModelArtifact | None":
        """Flip this row to PRODUCTION; archive any previous PRODUCTION row.

        Returns the previously-production artifact (now ARCHIVED) so the
        caller can surface a rollback option in the admin diff view.
        """
        if self.status == self.Status.PRODUCTION:
            return None
        previous = AtRiskModelArtifact.current_production()
        if previous is not None:
            previous.status = self.Status.ARCHIVED
            previous.save(update_fields=["status"])
        self.status = self.Status.PRODUCTION
        self.promoted_at = timezone.now()
        self.promoted_by = by_user
        self.save(update_fields=["status", "promoted_at", "promoted_by"])
        return previous


class AtRiskInferenceRun(models.Model):
    """One row per nightly batch — observability across runs.

    Drift, calibration, and capacity questions all eventually need a
    longitudinal record. Sentry traces alone aren't enough — they don't
    survive 30 days and don't aggregate well over months.
    """

    class Outcome(models.TextChoices):
        OK = "ok", "Completed normally"
        HEURISTIC_FALLBACK = "heuristic", "Ran heuristic (no ML model loaded)"
        PARTIAL = "partial", "Completed with errors on some schools"
        FAILED = "failed", "Failed before any scores were written"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="at_risk_inference_runs",
    )
    artifact = models.ForeignKey(
        AtRiskModelArtifact,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="inference_runs",
        help_text="Null when run ran on heuristic fallback or a path-pinned "
        "artifact that hasn't been registered.",
    )
    model_version_snapshot = models.CharField(
        max_length=120,
        blank=True,
        help_text="Resolved model_version at run time (denormalised so the "
        "row stays meaningful if the artifact row is later renamed).",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    students_scored = models.PositiveIntegerField(default=0)
    students_red_band = models.PositiveIntegerField(default=0)
    students_amber_band = models.PositiveIntegerField(default=0)
    students_green_band = models.PositiveIntegerField(default=0)
    mean_score = models.FloatField(null=True, blank=True)
    median_score = models.FloatField(null=True, blank=True)
    p95_score = models.FloatField(null=True, blank=True)
    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        default=Outcome.OK,
    )
    error_summary = models.TextField(blank=True, default="")

    class Meta:
        app_label = "analytics"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["school", "-started_at"]),
            models.Index(fields=["artifact", "-started_at"]),
        ]
        verbose_name = "At-risk inference run"
        verbose_name_plural = "At-risk inference runs"

    def __str__(self) -> str:
        return (
            f"{self.school_id}@{self.started_at:%Y-%m-%d} "
            f"n={self.students_scored} ({self.outcome})"
        )


class AtRiskShadowRun(models.Model):
    """One aggregate row per shadow comparison batch.

    Captures the answer to "what happens if we promote the current
    candidate?" — agreement, distribution drift between production and
    candidate, band-change counts. Drives the promote/reject decision in
    the admin dashboard.

    A shadow run exists only when BOTH a production AND a candidate
    artifact are registered; otherwise the command short-circuits.
    """

    class Outcome(models.TextChoices):
        OK = "ok", "Completed normally"
        SKIPPED = "skipped", "No candidate or no production to compare"
        FAILED = "failed", "Aborted with error"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="at_risk_shadow_runs",
    )
    production_artifact = models.ForeignKey(
        AtRiskModelArtifact,
        on_delete=models.PROTECT,
        related_name="shadow_runs_as_production",
    )
    candidate_artifact = models.ForeignKey(
        AtRiskModelArtifact,
        on_delete=models.PROTECT,
        related_name="shadow_runs_as_candidate",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    students_scored = models.PositiveIntegerField(default=0)
    band_changes = models.PositiveIntegerField(
        default=0,
        help_text="Number of students whose risk band differs between production and candidate.",
    )
    promotions = models.PositiveIntegerField(
        default=0,
        help_text="Candidate moved student to a HIGHER risk band (green→amber, amber→red).",
    )
    demotions = models.PositiveIntegerField(
        default=0,
        help_text="Candidate moved student to a LOWER risk band.",
    )
    agreement_pct = models.FloatField(
        null=True, blank=True,
        help_text="Share of students with identical bands across both models, [0.0, 1.0].",
    )
    mean_abs_delta = models.FloatField(null=True, blank=True)
    median_abs_delta = models.FloatField(null=True, blank=True)
    p95_abs_delta = models.FloatField(null=True, blank=True)
    psi_score_distribution = models.FloatField(
        null=True, blank=True,
        help_text="PSI between production and candidate score distributions (10 bins).",
    )
    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        default=Outcome.OK,
    )
    error_summary = models.TextField(blank=True, default="")

    class Meta:
        app_label = "analytics"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["school", "-started_at"]),
            models.Index(fields=["candidate_artifact", "-started_at"]),
        ]
        verbose_name = "At-risk shadow run"
        verbose_name_plural = "At-risk shadow runs"

    def __str__(self) -> str:
        return (
            f"{self.school_id} {self.production_artifact_id}→"
            f"{self.candidate_artifact_id} agreement={self.agreement_pct}"
        )


class AtRiskShadowComparison(models.Model):
    """Per-student production vs candidate score comparison.

    These rows are the audit trail behind aggregate shadow metrics.
    Operators can spot-check individual disagreements (the students who
    changed band) to decide whether the candidate's behaviour is an
    improvement or a regression.
    """

    run = models.ForeignKey(
        AtRiskShadowRun,
        on_delete=models.CASCADE,
        related_name="comparisons",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="at_risk_shadow_comparisons",
    )
    production_score = models.FloatField()
    candidate_score = models.FloatField()
    score_delta = models.FloatField(
        help_text="candidate_score - production_score (signed).",
    )
    production_band = models.CharField(max_length=10)
    candidate_band = models.CharField(max_length=10)
    band_changed = models.BooleanField(default=False)

    class Meta:
        app_label = "analytics"
        indexes = [
            models.Index(fields=["run", "-score_delta"]),
            models.Index(fields=["run", "band_changed"]),
        ]
        verbose_name = "At-risk shadow comparison"
        verbose_name_plural = "At-risk shadow comparisons"

    def __str__(self) -> str:
        return (
            f"{self.student_id} prod={self.production_score:.1f} "
            f"cand={self.candidate_score:.1f}"
        )
