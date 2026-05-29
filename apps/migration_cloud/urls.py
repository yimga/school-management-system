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

from django.urls import include, path

from . import (
    companion_receiver,
    views,
    views_audit_admin,
    views_command_center,
    views_connectors,
    views_dsar_admin,
    views_health,
    views_lms_diagnostics,
    views_maa_counsel_activate,
    views_maa_promotion,
    views_smoke_history,
    views_smoke_trigger,
    views_token_admin,
    views_webhook_admin,
)
# Wave 9 Agent N — vendor write-path authorization status (counsel-pending surface).
from .api import views_vendor_write_status as _views_vendor_write_status

app_name = "migration_cloud"

urlpatterns = [
    path("", views.MigrationCloudConsoleView.as_view(), name="console"),
    path("new/", views.MigrationCloudIntakeView.as_view(), name="bundle_new"),
    path("intake-ai-ask/", views.MigrationCloudIntakeAIAskView.as_view(), name="intake_ai_ask"),
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
    # Long-tail canonical template — the "Shopify CSV" path for any custom source.
    path("template/", views.MigrationCloudCanonicalTemplateView.as_view(), name="canonical_template_zip"),
    path("template/<str:domain>.csv", views.MigrationCloudCanonicalTemplateView.as_view(), name="canonical_template_csv"),
    path("template/picker/", views.MigrationCloudCanonicalTemplatePickerView.as_view(), name="canonical_template_picker"),
    # v3.27 — Migration Cloud public REST API alpha (DRF viewsets, OpenAPI-covered).
    path("api/v1/", include("apps.migration_cloud.api.urls")),
    # v3.29 — Companion-extension upload receiver + MAA consent.
    path("companion/maa/text/", companion_receiver.maa_text_view, name="companion_maa_text"),
    path("companion/maa/sign/", companion_receiver.MAASignView.as_view(), name="companion_maa_sign"),
    path("companion/upload/", companion_receiver.CompanionUploadView.as_view(), name="companion_upload"),
    path("companion/decrypt/<int:bundle_id>/", companion_receiver.CompanionDecryptHookView.as_view(), name="companion_decrypt"),
    # v3.32 — Companion server-side X25519 keypair distribution + rotation.
    path("companion/server-pubkey/", companion_receiver.companion_server_pubkey_view, name="companion_server_pubkey"),
    path("companion/keypair/rotate/", companion_receiver.CompanionKeypairRotateView.as_view(), name="companion_keypair_rotate"),
    # v3.32.0 — operator UI: scoped-API-token + outbound-webhook administration.
    # Staff-only. Each path carries `rbac-allow` so audit_role_permission_matrix
    # records the intentional staff-only gate.
    path("operator/tokens/", views_token_admin.MigrationCloudTokenListView.as_view(), name="operator_token_list"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/tokens/mint/", views_token_admin.MigrationCloudTokenMintView.as_view(), name="operator_token_mint"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/tokens/<int:token_id>/revoke/", views_token_admin.MigrationCloudTokenRevokeView.as_view(), name="operator_token_revoke"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/tokens/<int:token_id>/rotate/", views_token_admin.MigrationCloudTokenRotateView.as_view(), name="operator_token_rotate"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/tokens/<int:token_id>/chain/", views_token_admin.TokenRotationChainView.as_view(), name="operator_token_chain"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/webhooks/", views_webhook_admin.MigrationCloudWebhookListView.as_view(), name="operator_webhook_list"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/webhooks/subscribe/", views_webhook_admin.MigrationCloudWebhookSubscribeView.as_view(), name="operator_webhook_subscribe"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/webhooks/deliveries/", views_webhook_admin.MigrationCloudWebhookDeliveryLogView.as_view(), name="operator_webhook_delivery_log"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    path("operator/webhooks/deliveries/<int:delivery_id>/retry/", views_webhook_admin.MigrationCloudWebhookRetryView.as_view(), name="operator_webhook_delivery_retry"),  # rbac-allow: staff-only-operator-token-and-webhook-management
    # v3.37.0 Agent 5 — per-subscription audit + manual replay tooling.
    path("operator/webhooks/<int:sub_id>/audit/", views_webhook_admin.WebhookSubscriptionAuditView.as_view(), name="operator_webhook_audit"),  # rbac-allow: super-staff-webhook-audit-view-deliveries
    path("operator/webhooks/deliveries/<int:delivery_id>/replay/", views_webhook_admin.WebhookDeliveryReplayView.as_view(), name="operator_webhook_delivery_replay"),  # rbac-allow: super-staff-webhook-manual-replay
    # v3.39.0 Agent 2 — operator-side subscription deactivate (soft-delete) + emit reserved audit event.
    path("operator/webhooks/<int:sub_id>/deactivate/", views_webhook_admin.MigrationCloudWebhookDeactivateView.as_view(), name="operator_webhook_deactivate"),  # rbac-allow: super-staff-webhook-subscription-deactivate
    # v3.35.0 Agent 3 — MAA v2.0 promotion-readiness operator dashboard.
    path("maa-v2-promotion/", views_maa_promotion.MAA_V2_PromotionDashboardView.as_view(), name="maa_v2_promotion_dashboard"),  # rbac-allow: super-staff-view-maa-promotion-status
    # v3.40.0 Agent 15 — MAA v2.0 counsel-activate UI (operator GET + POST flip).
    path("maa/v2-counsel-activate/", views_maa_counsel_activate.MAACounselActivateView.as_view(), name="maa_counsel_activate"),  # rbac-allow: super-staff-maa-counsel-activate
    # v3.38.0 Agent 5 — tamper-evident audit log dashboard + JSONL export.
    path("audit/", views_audit_admin.MigrationCloudAuditView.as_view(), name="audit_dashboard"),  # rbac-allow: super-staff-audit-event-dashboard
    path("audit/export/", views_audit_admin.MigrationCloudAuditExportView.as_view(), name="audit_export"),  # rbac-allow: super-staff-audit-event-export
    # v3.38.0 Agent 4 — Migration Cloud operator health / status dashboard.
    # Reachable at /super/migration/health/ (operator mount) and the same
    # relative path under the portal mount; both shells render identically
    # because the view does not read per-shell tenant scope.
    path("health/", views_health.MigrationCloudHealthView.as_view(), name="migration_cloud_health"),  # rbac-allow: super-staff-migration-cloud-health-status
    # v4.00.56 — LMS connector diagnostics (token health + 24h refresh/rotation outcomes).
    path("lms/diagnostics/", views_lms_diagnostics.lms_diagnostics, name="migration_cloud_lms_diagnostics"),  # rbac-allow: super-staff-migration-cloud-lms-diagnostics
    # v4.00.59 — operator action buttons on the diagnostics dashboard.
    path("lms/diagnostics/force-refresh/", views_lms_diagnostics.lms_diagnostics_force_refresh, name="migration_cloud_lms_diagnostics_force_refresh"),  # rbac-allow: super-staff-migration-cloud-lms-force-refresh
    path("lms/diagnostics/force-rotate/", views_lms_diagnostics.lms_diagnostics_force_rotate, name="migration_cloud_lms_diagnostics_force_rotate"),  # rbac-allow: super-staff-migration-cloud-lms-force-rotate
    # v4.00.60 — last-action history JSON for the diagnostics dashboard panel.
    path("lms/diagnostics/action-history/", views_lms_diagnostics.lms_diagnostics_action_history, name="migration_cloud_lms_diagnostics_action_history"),  # rbac-allow: super-staff-migration-cloud-lms-action-history
    # v3.40.0 Agent 6 — Migration Cloud Command Center (8-card operator dashboard).
    path("command-center/", views_command_center.MigrationCloudCommandCenterView.as_view(), name="migration_cloud_command_center"),  # rbac-allow: super-staff-migration-cloud-command-center
    # Wave 9 Agent N — vendor write-path authorization status (counsel-pending shovel-ready surface).
    path("vendor-write-status/", _views_vendor_write_status.VendorWriteStatusView.as_view(), name="vendor_write_status"),  # rbac-allow: super-staff-vendor-write-authorization-status
    # v3.40.0 Agent 14 — "Run Smoke Now" operator trigger (form + Celery dispatch).
    path("smoke/trigger/", views_smoke_trigger.SmokeRunTriggerView.as_view(), name="smoke_run_trigger"),  # rbac-allow: super-staff-migration-cloud-smoke-on-demand-trigger
    # v3.40.0 Agent 13 — DSAR runbook recorder + smoke run history archive view.
    path("dsar/runbook/", views_dsar_admin.DSARRunbookView.as_view(), name="migration_cloud_dsar_runbook"),  # rbac-allow: super-staff-dsar-runbook-view-record
    path("smoke/history/", views_smoke_history.SmokeRunHistoryView.as_view(), name="migration_cloud_smoke_history"),  # rbac-allow: super-staff-migration-cloud-smoke-history
    # Connector wizard (operator mount mirrors tenant grammar under /connectors/).
    path(
        "connectors/",
        include(("apps.migration_cloud.urls_connectors", "migration_cloud_connector")),
    ),
    path(
        "connectors/operator/",
        views_connectors.MigrationCloudConnectorOperatorView.as_view(),
        name="connector_operator_dashboard",
    ),  # rbac-allow: super-staff-migration-cloud-connector-operator
]
