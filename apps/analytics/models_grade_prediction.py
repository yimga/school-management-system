"""Grade prediction — second ML use case (Wave 4).

Predicts end-of-term grade for (student, subject, term) from mid-term
signals: prior-term grade average, attendance, evaluation trend,
incident count. Reuses the registry / inference-run / shadow pattern
from the at-risk model — see [[ai-ml-wave-1-mlops-registry-v2-92]] —
but lives as a parallel family to keep schemas clean.

Three models in this module:
  * `GradePredictionLabel` — operator-supplied ground truth
    (final grade at term close).
  * `GradePrediction` — per-(student, subject, term) prediction row.
  * `GradePredictionModelArtifact` — mirror of AtRiskModelArtifact for
    this task family. Identical lifecycle: candidate → production →
    archived/rejected.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class GradePredictionModelArtifact(models.Model):
    """Registry row for one trained grade-prediction artifact."""

    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        PRODUCTION = "production", "Production"
        ARCHIVED = "archived", "Archived"
        REJECTED = "rejected", "Rejected"

    model_version = models.CharField(max_length=120, unique=True)
    artifact_path = models.CharField(max_length=512)
    trained_at = models.DateTimeField()
    training_dataset_hash = models.CharField(max_length=64, blank=True)
    training_row_count = models.PositiveIntegerField(default=0)
    feature_order = models.JSONField(default=list)
    metric_mae = models.FloatField(null=True, blank=True,
        help_text="Mean Absolute Error on holdout (regression metric).",
    )
    metric_rmse = models.FloatField(null=True, blank=True,
        help_text="Root Mean Squared Error on holdout.",
    )
    metric_r2 = models.FloatField(null=True, blank=True,
        help_text="Coefficient of determination R² on holdout, [-∞, 1.0].",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CANDIDATE,
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="grade_prediction_artifacts_registered",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    promoted_at = models.DateTimeField(null=True, blank=True)
    promoted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="grade_prediction_artifacts_promoted",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        app_label = "analytics"
        ordering = ["-registered_at"]
        indexes = [
            models.Index(fields=["status", "-registered_at"]),
        ]
        verbose_name = "Grade prediction model artifact"
        verbose_name_plural = "Grade prediction model artifacts"

    def __str__(self) -> str:
        return f"{self.model_version} [{self.status}]"

    @classmethod
    def current_production(cls):
        return cls.objects.filter(status=cls.Status.PRODUCTION).order_by(
            "-promoted_at"
        ).first()

    @transaction.atomic
    def promote(self, *, by_user):
        if self.status == self.Status.PRODUCTION:
            return None
        previous = GradePredictionModelArtifact.current_production()
        if previous is not None:
            previous.status = self.Status.ARCHIVED
            previous.save(update_fields=["status"])
        self.status = self.Status.PRODUCTION
        self.promoted_at = timezone.now()
        self.promoted_by = by_user
        self.save(update_fields=["status", "promoted_at", "promoted_by"])
        return previous


class GradePredictionLabel(models.Model):
    """Operator-supplied truth: the final grade at term close.

    Joins to GradePrediction at training-export time to form
    (features, label) tuples consumable by the trainer. Scoped
    (student, subject, academic_year, term) — unique constraint
    prevents conflicting labels for the same period.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="grade_prediction_labels",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="grade_prediction_labels",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="grade_prediction_labels",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="grade_prediction_labels",
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.PROTECT,
        related_name="grade_prediction_labels",
    )
    actual_grade = models.FloatField(
        help_text="End-of-term grade, scale 0-100 normalised.",
    )
    labeled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="grade_prediction_labels_set",
    )
    labeled_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        app_label = "analytics"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "academic_year", "term"],
                name="uniq_grade_pred_label",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "academic_year", "term"]),
            models.Index(fields=["student"]),
        ]
        ordering = ["-labeled_at"]
        verbose_name = "Grade prediction label"
        verbose_name_plural = "Grade prediction labels"

    def __str__(self) -> str:
        return (
            f"{self.student_id}/{self.subject_id}/{self.term_id}"
            f"={self.actual_grade:.1f}"
        )


class GradePrediction(models.Model):
    """One predicted grade per (student, subject, term).

    Latest row wins via `update_or_create` keyed on the four scoping
    fields; previous predictions for the same scope are not retained
    (operators care about the current outlook, not historical
    revisions — those live in the audit log).
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="grade_predictions",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="grade_predictions",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="grade_predictions",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="grade_predictions",
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.PROTECT,
        related_name="grade_predictions",
    )
    predicted_grade = models.FloatField(
        help_text="Predicted end-of-term grade, scale 0-100.",
    )
    confidence_low = models.FloatField(
        null=True, blank=True,
        help_text="Lower 90% confidence bound (heuristic ± 1 SD).",
    )
    confidence_high = models.FloatField(
        null=True, blank=True,
        help_text="Upper 90% confidence bound.",
    )
    reason_summary = models.CharField(max_length=500, blank=True)
    model_version = models.CharField(max_length=80, blank=True)
    feature_contributions = models.JSONField(default=list, blank=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "analytics"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "academic_year", "term"],
                name="uniq_grade_pred_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "-computed_at"]),
            models.Index(fields=["academic_year", "term"]),
        ]
        ordering = ["-computed_at"]

    def __str__(self) -> str:
        return (
            f"{self.student_id}/{self.subject_id}/{self.term_id}"
            f"={self.predicted_grade:.1f}"
        )


class GradePredictionShadowRun(models.Model):
    """Aggregate row for one grade-prediction shadow batch."""

    class Outcome(models.TextChoices):
        OK = "ok", "Completed normally"
        SKIPPED = "skipped", "No candidate or no production"
        FAILED = "failed", "Aborted with error"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="grade_pred_shadow_runs",
    )
    production_artifact = models.ForeignKey(
        GradePredictionModelArtifact,
        on_delete=models.PROTECT,
        related_name="grade_shadow_runs_as_production",
    )
    candidate_artifact = models.ForeignKey(
        GradePredictionModelArtifact,
        on_delete=models.PROTECT,
        related_name="grade_shadow_runs_as_candidate",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    rows_compared = models.PositiveIntegerField(default=0)
    mean_abs_delta = models.FloatField(null=True, blank=True)
    median_abs_delta = models.FloatField(null=True, blank=True)
    p95_abs_delta = models.FloatField(null=True, blank=True)
    bias = models.FloatField(
        null=True, blank=True,
        help_text="mean(candidate - production); persistent positive = candidate is more optimistic.",
    )
    outcome = models.CharField(
        max_length=20, choices=Outcome.choices, default=Outcome.OK,
    )
    error_summary = models.TextField(blank=True, default="")

    class Meta:
        app_label = "analytics"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["school", "-started_at"]),
        ]


class GradePredictionShadowComparison(models.Model):
    """Per (student, subject, term) prediction comparison row."""

    run = models.ForeignKey(
        GradePredictionShadowRun,
        on_delete=models.CASCADE,
        related_name="comparisons",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="grade_pred_shadow_comparisons",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="grade_pred_shadow_comparisons",
    )
    production_grade = models.FloatField()
    candidate_grade = models.FloatField()
    grade_delta = models.FloatField(
        help_text="candidate_grade - production_grade",
    )

    class Meta:
        app_label = "analytics"
        indexes = [
            models.Index(fields=["run", "-grade_delta"]),
        ]
