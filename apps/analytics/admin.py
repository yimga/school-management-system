from django.contrib import admin, messages

from config.admin import register_tenant_admin

from unfold.admin import ModelAdmin

from .models import (
    AtRiskInferenceRun,
    AtRiskModelArtifact,
    AtRiskShadowComparison,
    AtRiskShadowRun,
    BenchmarkAggregate,
    GovernedSavedReport,
    GradePrediction,
    GradePredictionLabel,
    GradePredictionModelArtifact,
    GradePredictionShadowComparison,
    GradePredictionShadowRun,
    RiskDigestRecipient,
)


class BenchmarkAggregateAdmin(ModelAdmin):
    list_display = (
        "region_code",
        "sub_system",
        "subject_id",
        "term_id",
        "metric",
        "value",
        "sample_size",
    )
    list_filter = ("region_code", "sub_system", "metric")


register_tenant_admin(BenchmarkAggregate, BenchmarkAggregateAdmin)


class GovernedSavedReportAdmin(ModelAdmin):
    list_display = ("name", "school", "updated_at", "created_by")
    list_filter = ("school",)
    search_fields = ("name",)


register_tenant_admin(GovernedSavedReport, GovernedSavedReportAdmin)


@admin.action(description="Promote selected artifact to PRODUCTION")
def _promote_artifact(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            "Pick exactly one artifact to promote (avoid accidental double-flips).",
            level=messages.ERROR,
        )
        return
    artifact = queryset.first()
    if artifact.status == AtRiskModelArtifact.Status.REJECTED:
        modeladmin.message_user(
            request,
            f"{artifact.model_version} is REJECTED — promote via CLI with "
            "--allow-rejected if you really mean to.",
            level=messages.ERROR,
        )
        return
    previous = artifact.promote(by_user=request.user)
    if previous is None:
        modeladmin.message_user(
            request,
            f"Promoted {artifact.model_version}; no previous production row.",
            level=messages.SUCCESS,
        )
    else:
        modeladmin.message_user(
            request,
            f"Promoted {artifact.model_version}; archived {previous.model_version}.",
            level=messages.SUCCESS,
        )


@admin.action(description="Reject selected candidate artifact(s)")
def _reject_artifact(modeladmin, request, queryset):
    n = 0
    for artifact in queryset:
        if artifact.status == AtRiskModelArtifact.Status.PRODUCTION:
            continue  # rejecting the current production row would leave loader without one
        artifact.status = AtRiskModelArtifact.Status.REJECTED
        artifact.save(update_fields=["status"])
        n += 1
    modeladmin.message_user(
        request, f"Rejected {n} artifact(s).", level=messages.SUCCESS
    )


class AtRiskModelArtifactAdmin(ModelAdmin):
    list_display = (
        "model_version", "status", "metric_roc_auc",
        "metric_average_precision", "metric_ece",
        "trained_at", "registered_at", "promoted_at",
    )
    list_filter = ("status",)
    search_fields = ("model_version", "artifact_path", "notes")
    readonly_fields = (
        "registered_at", "promoted_at", "promoted_by",
        "training_dataset_hash", "training_row_count", "feature_order",
    )
    actions = [_promote_artifact, _reject_artifact]


class AtRiskInferenceRunAdmin(ModelAdmin):
    list_display = (
        "school", "started_at", "model_version_snapshot", "outcome",
        "students_scored", "students_red_band",
        "students_amber_band", "students_green_band",
        "mean_score", "median_score", "p95_score",
    )
    list_filter = ("outcome", "school")
    search_fields = ("model_version_snapshot", "error_summary")
    readonly_fields = tuple(
        f.name for f in AtRiskInferenceRun._meta.fields
    )

    def has_add_permission(self, request):
        # Inference runs are emitted by the nightly job; never hand-added.
        return False


register_tenant_admin(AtRiskModelArtifact, AtRiskModelArtifactAdmin)
register_tenant_admin(AtRiskInferenceRun, AtRiskInferenceRunAdmin)


@admin.action(description="Promote candidate to PRODUCTION (from shadow row)")
def _promote_candidate_from_shadow(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            "Pick exactly one shadow run to promote its candidate.",
            level=messages.ERROR,
        )
        return
    run = queryset.first()
    if run.outcome != AtRiskShadowRun.Outcome.OK:
        modeladmin.message_user(
            request,
            f"Shadow run is in state '{run.outcome}'; only OK runs can drive a promote.",
            level=messages.ERROR,
        )
        return
    candidate = run.candidate_artifact
    previous = candidate.promote(by_user=request.user)
    if previous is None:
        modeladmin.message_user(
            request,
            f"Promoted {candidate.model_version} from shadow evidence; no prior production row.",
            level=messages.SUCCESS,
        )
    else:
        modeladmin.message_user(
            request,
            f"Promoted {candidate.model_version} from shadow evidence; "
            f"archived {previous.model_version}.",
            level=messages.SUCCESS,
        )


class AtRiskShadowRunAdmin(ModelAdmin):
    list_display = (
        "school", "started_at", "production_artifact", "candidate_artifact",
        "outcome", "students_scored", "agreement_pct",
        "band_changes", "promotions", "demotions",
        "psi_score_distribution",
    )
    list_filter = ("outcome", "school")
    readonly_fields = tuple(
        f.name for f in AtRiskShadowRun._meta.fields
    )
    actions = [_promote_candidate_from_shadow]

    def has_add_permission(self, request):
        return False


class AtRiskShadowComparisonAdmin(ModelAdmin):
    list_display = (
        "run", "student", "production_score", "candidate_score",
        "score_delta", "production_band", "candidate_band", "band_changed",
    )
    list_filter = ("band_changed", "production_band", "candidate_band")
    search_fields = ("student__first_name", "student__last_name")
    readonly_fields = tuple(
        f.name for f in AtRiskShadowComparison._meta.fields
    )

    def has_add_permission(self, request):
        return False


register_tenant_admin(AtRiskShadowRun, AtRiskShadowRunAdmin)
register_tenant_admin(AtRiskShadowComparison, AtRiskShadowComparisonAdmin)


@admin.action(description="Promote grade-prediction artifact to PRODUCTION")
def _promote_grade_artifact(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(
            request, "Pick exactly one artifact.", level=messages.ERROR,
        )
        return
    artifact = queryset.first()
    previous = artifact.promote(by_user=request.user)
    msg = f"Promoted {artifact.model_version}"
    if previous is not None:
        msg += f"; archived {previous.model_version}"
    modeladmin.message_user(request, msg + ".", level=messages.SUCCESS)


class GradePredictionModelArtifactAdmin(ModelAdmin):
    list_display = (
        "model_version", "status",
        "metric_mae", "metric_rmse", "metric_r2",
        "trained_at", "promoted_at",
    )
    list_filter = ("status",)
    search_fields = ("model_version", "notes")
    readonly_fields = (
        "registered_at", "promoted_at", "promoted_by",
        "training_dataset_hash", "training_row_count", "feature_order",
    )
    actions = [_promote_grade_artifact]


class GradePredictionLabelAdmin(ModelAdmin):
    list_display = (
        "student", "subject", "term", "academic_year",
        "actual_grade", "labeled_by", "labeled_at",
    )
    list_filter = ("school", "academic_year", "term")
    search_fields = ("student__first_name", "student__last_name")
    autocomplete_fields = ()
    readonly_fields = ("labeled_at",)


class GradePredictionAdmin(ModelAdmin):
    list_display = (
        "student", "subject", "term", "academic_year",
        "predicted_grade", "model_version", "computed_at",
    )
    list_filter = ("school", "academic_year", "term", "model_version")
    search_fields = ("student__first_name", "student__last_name")
    readonly_fields = tuple(
        f.name for f in GradePrediction._meta.fields
    )

    def has_add_permission(self, request):
        return False


register_tenant_admin(
    GradePredictionModelArtifact, GradePredictionModelArtifactAdmin,
)
register_tenant_admin(GradePredictionLabel, GradePredictionLabelAdmin)
register_tenant_admin(GradePrediction, GradePredictionAdmin)


@admin.action(description="Promote grade-prediction candidate from shadow row")
def _promote_grade_candidate_from_shadow(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(
            request, "Pick exactly one shadow run.", level=messages.ERROR,
        )
        return
    run = queryset.first()
    if run.outcome != GradePredictionShadowRun.Outcome.OK:
        modeladmin.message_user(
            request,
            f"Shadow run is '{run.outcome}'; only OK runs can drive a promote.",
            level=messages.ERROR,
        )
        return
    candidate = run.candidate_artifact
    previous = candidate.promote(by_user=request.user)
    msg = f"Promoted grade-prediction {candidate.model_version}"
    if previous is not None:
        msg += f"; archived previous {previous.model_version}"
    modeladmin.message_user(request, msg + ".", level=messages.SUCCESS)


class GradePredictionShadowRunAdmin(ModelAdmin):
    list_display = (
        "school", "started_at", "production_artifact", "candidate_artifact",
        "outcome", "rows_compared", "mean_abs_delta", "bias",
    )
    list_filter = ("outcome", "school")
    readonly_fields = tuple(
        f.name for f in GradePredictionShadowRun._meta.fields
    )
    actions = [_promote_grade_candidate_from_shadow]

    def has_add_permission(self, request):
        return False


class GradePredictionShadowComparisonAdmin(ModelAdmin):
    list_display = (
        "run", "student", "subject",
        "production_grade", "candidate_grade", "grade_delta",
    )
    list_filter = ("run",)
    search_fields = ("student__first_name", "student__last_name")
    readonly_fields = tuple(
        f.name for f in GradePredictionShadowComparison._meta.fields
    )

    def has_add_permission(self, request):
        return False


register_tenant_admin(GradePredictionShadowRun, GradePredictionShadowRunAdmin)
register_tenant_admin(
    GradePredictionShadowComparison, GradePredictionShadowComparisonAdmin,
)


class RiskDigestRecipientAdmin(ModelAdmin):
    list_display = ("school", "channel", "label", "target", "enabled", "created_at")
    list_filter = ("school", "channel", "enabled")
    search_fields = ("target", "label")
    list_editable = ("enabled",)


register_tenant_admin(RiskDigestRecipient, RiskDigestRecipientAdmin)
