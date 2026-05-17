"""URL grammar for the Migration Cloud wizard.

Mounted twice from ``config/urls.py`` — once under ``/super/migration/``
(operator) and once under ``/portal/configure/migration/`` (tenant,
plan-gated). The single URL set + ``shell`` kwarg keeps view logic
unified.

Example mount in ``config/urls.py``::

    path("super/migration/", include(("apps.migration_cloud.urls", "migration_cloud_super"), namespace="migration_cloud_super"), {"shell": "super"}),
    path("portal/configure/migration/", include(("apps.migration_cloud.urls", "migration_cloud_portal"), namespace="migration_cloud_portal"), {"shell": "portal"}),
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "migration_cloud"

urlpatterns = [
    path("", views.MigrationCloudConsoleView.as_view(), name="console"),
    path("new/", views.MigrationCloudIntakeView.as_view(), name="bundle_new"),
    path("<int:bundle_id>/", views.MigrationCloudBundleDetailView.as_view(), name="bundle_detail"),
    path("<int:bundle_id>/attach-source/", views.MigrationCloudAttachSourceView.as_view(), name="bundle_attach_source"),
    path("<int:bundle_id>/bind-school/", views.MigrationCloudBindSchoolView.as_view(), name="bundle_bind_school"),
    path("<int:bundle_id>/ai-plan/", views.MigrationCloudAIPlanView.as_view(), name="bundle_ai_plan"),
    path("<int:bundle_id>/ai-explain/", views.MigrationCloudAIExplainView.as_view(), name="bundle_ai_explain"),
    path("<int:bundle_id>/ai-rebind/", views.MigrationCloudAIRebindView.as_view(), name="bundle_ai_rebind"),
    path("<int:bundle_id>/ai-ask/", views.MigrationCloudAIAskView.as_view(), name="bundle_ai_ask"),
    path("<int:bundle_id>/ai-narrate-reconciliation/", views.MigrationCloudAINarrateReconciliationView.as_view(), name="bundle_ai_narrate_reconciliation"),
    path("ai-vendor-from-image/", views.MigrationCloudAIVendorFromImageView.as_view(), name="ai_vendor_from_image"),
    path("<int:bundle_id>/advance/", views.MigrationCloudAdvanceView.as_view(), name="bundle_advance"),
    path("<int:bundle_id>/apply/", views.MigrationCloudApplyView.as_view(), name="bundle_apply"),
    path("<int:bundle_id>/reconcile/", views.MigrationCloudReconcileView.as_view(), name="bundle_reconcile"),
    path("<int:bundle_id>/feedback/", views.MigrationCloudFeedbackView.as_view(), name="bundle_feedback"),
    path("<int:bundle_id>/save-profile/", views.MigrationCloudSaveProfileView.as_view(), name="bundle_save_profile"),
    path("<int:bundle_id>/review/", views.MigrationCloudAnomalyNudgeView.as_view(), name="bundle_review"),
    path("<int:bundle_id>/shadow/", views.MigrationCloudShadowView.as_view(), name="bundle_shadow"),
    path("<int:bundle_id>/runs/<int:run_id>/rollback/", views.MigrationCloudRollbackView.as_view(), name="run_rollback"),
    # sms-v3.7 — Tier 1 / Tier 2 / Tier 3
    path("<int:bundle_id>/expected-totals/", views.MigrationCloudExpectedTotalsView.as_view(), name="bundle_expected_totals"),
    path("<int:bundle_id>/guardrail-check/", views.MigrationCloudGuardrailCheckView.as_view(), name="bundle_guardrail_check"),
    path("id-map/lookup/", views.MigrationCloudIdMappingLookupView.as_view(), name="id_mapping_lookup"),
    path("<int:bundle_id>/conflicts/", views.MigrationCloudConflictsView.as_view(), name="bundle_conflicts"),
    path("<int:bundle_id>/progress/", views.MigrationCloudProgressView.as_view(), name="bundle_progress"),
    path("<int:bundle_id>/progress/stream/", views.MigrationCloudProgressStreamView.as_view(), name="bundle_progress_stream"),
    path("<int:bundle_id>/preflight/", views.MigrationCloudPreflightView.as_view(), name="bundle_preflight"),
    path("<int:bundle_id>/assets/", views.MigrationCloudAssetsView.as_view(), name="bundle_assets"),
    path("<int:bundle_id>/sandbox/", views.MigrationCloudSandboxView.as_view(), name="bundle_sandbox"),
    path("<int:bundle_id>/diff-mode/", views.MigrationCloudDiffModeView.as_view(), name="bundle_diff_mode"),
    path("<int:bundle_id>/settings/", views.MigrationCloudBundleSettingsView.as_view(), name="bundle_settings"),
    path("<int:bundle_id>/cost-estimate/", views.MigrationCloudCostEstimateView.as_view(), name="bundle_cost_estimate"),
    path("profile-suggest/", views.MigrationCloudProfileSuggestView.as_view(), name="profile_suggest"),
    path("<int:bundle_id>/handoff-doc/", views.MigrationCloudHandoffDocView.as_view(), name="bundle_handoff_doc"),
    path("<int:bundle_id>/legacy-lockout/", views.MigrationCloudLegacyLockoutView.as_view(), name="bundle_legacy_lockout"),
    path("export/canonical/", views.MigrationCloudExportCanonicalView.as_view(), name="export_canonical"),
    path("<int:bundle_id>/rollout/", views.MigrationCloudRolloutPlanView.as_view(), name="bundle_rollout"),
    path("<int:bundle_id>/sla-targets/", views.MigrationCloudSlaTargetsView.as_view(), name="bundle_sla_targets"),
    path("merge/", views.MigrationCloudMergeBundlesView.as_view(), name="merge_bundles"),
]
