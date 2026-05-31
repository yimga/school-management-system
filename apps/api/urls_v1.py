"""
RunMyCampus Standards Compliance: API v1 URL contract.
Mount under path('api/v1/', include('apps.api.urls_v1')).
"""

from django.urls import path
from apps.api import views_v1, views_v1_intervention, views_v1_platform
from apps.api.api_v1_manifest import api_v1_manifest
from apps.api.views_webhook_catalog import WebhookEventTypesView
from apps.api.views_marketplace_catalog import (
    MarketplaceAppsListView,
    MarketplaceScopesListView,
)
from apps.api.views_marketplace_submissions import MarketplaceSubmissionView
from apps.api.views_migration_jobs import (
    MigrationJobErrorsCsvView,
    MigrationJobStatusView,
)
from apps.social_media.api_views import (
    SocialAnalyticsPulseAPI,
    SocialAttributionAPI,
    SocialFeedAPI,
    SocialModerationAPI,
    SocialPublishAPI,
)
# v3.62.2 (2026-05-22) — country-adaptive signup form (Wave 1 local-first).
from apps.siteconfig.views_country_localization import country_localization_pack
# v4.00.0 — canonical runtime endpoints fronted by the Cloudflare Worker.
from apps.api.runtime_endpoints import (
    feature_flags_runtime,
    grading_matrix_runtime,
    runtime_defaults_snapshot,
    school_calendar_runtime,
    site_settings_snapshot,
    structural_options_initialize_runtime,
    structural_options_runtime,
)

app_name = "api_v1"

from apps.sync_engine.views_crdt import CRDTOpsApplyView
from apps.platform_runtime.views_operator_tenant_inspect import OperatorTenantInspectView


urlpatterns = [
    path("manifest.json", api_v1_manifest, name="manifest"),
    # v4.00.13: CRDT ops merge endpoint (per-tenant LWW/ORSet/GCounter state).
    path("crdt/apply/", CRDTOpsApplyView.as_view(), name="crdt-apply"),
    # v4.00.0 zero-latency runtime endpoints (SWR-cached at the edge).
    path("runtime/calendar", school_calendar_runtime, name="runtime-calendar"),
    path("runtime/grading-matrix", grading_matrix_runtime, name="runtime-grading-matrix"),
    path("runtime/defaults", runtime_defaults_snapshot, name="runtime-defaults"),
    path("runtime/site-settings", site_settings_snapshot, name="runtime-site-settings"),
    path("runtime/feature-flags", feature_flags_runtime, name="runtime-feature-flags"),
    path("runtime/structural-options", structural_options_runtime, name="runtime-structural-options"),
    path(
        "runtime/structural-options/initialize",
        structural_options_initialize_runtime,
        name="runtime-structural-options-initialize",
    ),
    # Pass 12: public webhook event-type catalog backed by apps.events.catalog.
    path(
        "webhooks/event-types/",
        WebhookEventTypesView.as_view(),
        name="webhooks-event-types",
    ),
    # Pass 14: public marketplace catalog (apps + scope vocabulary).
    path(
        "marketplace/apps/",
        MarketplaceAppsListView.as_view(),
        name="marketplace-apps",
    ),
    path(
        "marketplace/scopes/",
        MarketplaceScopesListView.as_view(),
        name="marketplace-scopes",
    ),
    # Pass 14.C: publisher-facing app submission endpoint.
    path(
        "marketplace/submissions/",
        MarketplaceSubmissionView.as_view(),
        name="marketplace-submissions",
    ),
    # Pass 8.B: live progress snapshot for an async migration job.
    path(
        "migration-jobs/<str:job_id>/",
        MigrationJobStatusView.as_view(),
        name="migration-job-status",
    ),
    # Pass 8.D: CSV error-report download for the same migration job snapshot.
    path(
        "migration-jobs/<str:job_id>/errors.csv",
        MigrationJobErrorsCsvView.as_view(),
        name="migration-job-errors-csv",
    ),
    path(  # rbac-allow: api-key middleware-auth (request.app_api_key / oauth_access_pair)
        "platform/integration-context/",
        views_v1_platform.IntegrationContextView.as_view(),
        name="platform-integration-context",
    ),
    path(  # rbac-allow: api-key middleware-auth (request.app_api_key / oauth_access_pair)
        "platform/scoped-ping/",
        views_v1_platform.IntegrationScopedPingView.as_view(),
        name="platform-scoped-ping",
    ),
    path("me/schools", views_v1.MeSchoolsView.as_view(), name="me-schools"),
    path(
        "me/switch-school",
        views_v1.MeSwitchSchoolView.as_view(),
        name="me-switch-school",
    ),
    path(
        "tenants/provision",
        views_v1.TenantsProvisionView.as_view(),
        name="tenants-provision",
    ),
    path(
        "config/education-dna",
        views_v1.EducationDNAView.as_view(),
        name="config-education-dna",
    ),
    path(
        "config/education-templates",
        views_v1.EducationTemplatesView.as_view(),
        name="config-education-templates",
    ),
    path(
        "config/integration-catalog",
        views_v1.IntegrationCatalogView.as_view(),
        name="config-integration-catalog",
    ),
    path(
        "config/risk-thresholds",
        views_v1.RiskThresholdsConfigView.as_view(),
        name="config-risk-thresholds",
    ),
    path(  # rbac-allow: api-key middleware-auth (B2B integration context)
        "tenants/<uuid:id>/modules",
        views_v1.TenantModulesView.as_view(),
        name="tenants-modules",
    ),
    path(
        "student/passport/<uuid:global_id>",
        views_v1.StudentPassportView.as_view(),
        name="student-passport",
    ),
    path(
        "student/transfer",
        views_v1.StudentTransferView.as_view(),
        name="student-transfer",
    ),
    path(  # rbac-allow: api-key middleware-auth (B2B finance integration)
        "finance/generate-batch",
        views_v1.FinanceGenerateBatchView.as_view(),
        name="finance-generate-batch",
    ),
    path(  # rbac-allow: api-key middleware-auth (B2B finance integration)
        "finance/exchange-rate",
        views_v1.FinanceExchangeRateView.as_view(),
        name="finance-exchange-rate",
    ),
    path(
        "intervention/red-flags",
        views_v1_intervention.InterventionRedFlagsView.as_view(),
        name="intervention-red-flags",
    ),
    path(
        "intervention/action-center",
        views_v1_intervention.InterventionActionCenterView.as_view(),
        name="intervention-action-center",
    ),
    path(
        "intervention/action-center/<int:id>",
        views_v1_intervention.InterventionActionCenterDetailView.as_view(),
        name="intervention-action-center-detail",
    ),
    path(
        "intervention/calculate-risk",
        views_v1_intervention.InterventionCalculateRiskView.as_view(),
        name="intervention-calculate-risk",
    ),
    path(
        "intervention/generate-roadmap",
        views_v1_intervention.InterventionGenerateRoadmapView.as_view(),
        name="intervention-generate-roadmap",
    ),
    path(  # rbac-allow: api-key middleware-auth (B2B applicant intake)
        "enrollment/apply",
        views_v1.EnrollmentApplyView.as_view(),
        name="enrollment-apply",
    ),
    path(
        "attendance/bulk", views_v1.AttendanceBulkView.as_view(), name="attendance-bulk"
    ),
    path(
        "attendance/export",
        views_v1.AttendanceExportView.as_view(),
        name="attendance-export",
    ),
    path(
        "vocational/log-hours",
        views_v1.VocationalLogHoursView.as_view(),
        name="vocational-log-hours",
    ),
    path(
        "vocational/verify-skill",
        views_v1.VocationalVerifySkillView.as_view(),
        name="vocational-verify-skill",
    ),
    path(
        "vocational/digital-badge/<int:student_id>",
        views_v1.VocationalDigitalBadgeView.as_view(),
        name="vocational-digital-badge",
    ),
    path(
        "vocational/certifications-expiring",
        views_v1.VocationalCertificationsExpiringView.as_view(),
        name="vocational-certifications-expiring",
    ),
    path(
        "scheduler/generate",
        views_v1.SchedulerGenerateView.as_view(),
        name="scheduler-generate",
    ),
    path(
        "scheduler/validate",
        views_v1.SchedulerValidateView.as_view(),
        name="scheduler-validate",
    ),
    path(
        "syllabus/pacing", views_v1.SyllabusPacingView.as_view(), name="syllabus-pacing"
    ),
    path("super/pulse", views_v1.SuperPulseView.as_view(), name="super-pulse"),
    path("super/usage", views_v1.SuperUsageView.as_view(), name="super-usage"),
    path(
        "super/recovery-rate",
        views_v1.SuperRecoveryRateView.as_view(),
        name="super-recovery-rate",
    ),
    path(
        "super/tenant-health",
        views_v1.SuperTenantHealthView.as_view(),
        name="super-tenant-health",
    ),
    # v4.00.14: JIT-gated operator tenant inspector (compose JIT + GDPR + mask).
    path(
        "super/tenant-inspect/<int:school_id>/",
        OperatorTenantInspectView.as_view(),
        name="super-tenant-inspect",
    ),
    path(
        "super/schools",
        views_v1.SuperSchoolsListView.as_view(),
        name="super-schools-list",
    ),
    # Plan XII: GDPR "Export my school data"
    path(
        "compliance/export-school",
        views_v1.ComplianceExportSchoolView.as_view(),
        name="compliance-export-school",
    ),
    # Plan XVII: Enrollment forecasting stub
    path(
        "enrollment/forecast",
        views_v1.EnrollmentForecastView.as_view(),
        name="enrollment-forecast",
    ),
    # Plan III/XXI: Rosetta Stone (cross-tenant grade conversion)
    path(
        "rosetta/convert", views_v1.RosettaConvertView.as_view(), name="rosetta-convert"
    ),
    path("rosetta/scales", views_v1.RosettaScalesView.as_view(), name="rosetta-scales"),
    # Plan V: Parent Wallet top-up
    path(  # rbac-allow: api-key middleware-auth (B2B wallet top-up)
        "finance/wallet/top-up",
        views_v1.FinanceWalletTopUpView.as_view(),
        name="finance-wallet-top-up",
    ),
    # Plan IV: MoE / Regulatory Export presets
    path(
        "reports/regulatory-presets",
        views_v1.RegulatoryPresetsView.as_view(),
        name="reports-regulatory-presets",
    ),
    path(
        "reports/regulatory-export",
        views_v1.RegulatoryExportView.as_view(),
        name="reports-regulatory-export",
    ),
    # Plan II: Attendance bulk PATCH
    path(
        "attendance/bulk-update",
        views_v1.AttendanceBulkUpdateView.as_view(),
        name="attendance-bulk-update",
    ),
    # REFINEMENT commercial: quote-to-contract
    path(
        "billing/quote/<int:quote_id>/accept",
        views_v1.BillingQuoteAcceptView.as_view(),
        name="billing-quote-accept",
    ),
    # Phase 9: Payment dispute flow
    path(
        "finance/disputes",
        views_v1.PaymentDisputeListView.as_view(),
        name="finance-disputes-list",
    ),
    path(  # rbac-allow: api-key middleware-auth (B2B dispute intake)
        "finance/disputes/create",
        views_v1.PaymentDisputeCreateView.as_view(),
        name="finance-disputes-create",
    ),
    path(
        "finance/disputes/<uuid:id>",
        views_v1.PaymentDisputeResolveView.as_view(),
        name="finance-disputes-resolve",
    ),
    # Tenant scheduled-report delivery (hub + list; persistence phased after BI model cutover)
    path(  # rbac-allow: api-key middleware-auth (B2B scheduled-report consumer)
        "reports/scheduled",
        views_v1.ScheduledReportsListView.as_view(),
        name="reports-scheduled-list",
    ),
    path(  # rbac-allow: api-key middleware-auth (B2B scheduled-report consumer)
        "reports/scheduled/<int:id>",
        views_v1.ScheduledReportDetailView.as_view(),
        name="reports-scheduled-detail",
    ),
    # Phase 9: Ad-hoc report builder
    path(
        "reports/adhoc",
        views_v1.AdHocReportListCreateView.as_view(),
        name="reports-adhoc-list-create",
    ),
    path(
        "reports/adhoc/<int:id>/run",
        views_v1.AdHocReportRunView.as_view(),
        name="reports-adhoc-run",
    ),
    # Phase 9: Video attendance sync
    path(
        "video/sessions",
        views_v1.VideoSessionListCreateView.as_view(),
        name="video-sessions-list-create",
    ),
    path(
        "video/sessions/<int:id>/attendance-sync",
        views_v1.VideoAttendanceSyncView.as_view(),
        name="video-attendance-sync",
    ),
    # Nested tenancy: list child schools (campus switcher)
    path(
        "tenants/children",
        views_v1.TenantChildrenView.as_view(),
        name="tenants-children",
    ),
    # Government/District EMIS: prepare and submit
    path(
        "reports/emis/prepare",
        views_v1.EMISPrepareView.as_view(),
        name="reports-emis-prepare",
    ),
    path(
        "reports/emis/<int:id>/submit",
        views_v1.EMISSubmitView.as_view(),
        name="reports-emis-submit",
    ),
    # Social media integration (dual-tier feed + publish + moderation)
    path("social/feed/", SocialFeedAPI.as_view(), name="social-feed"),
    path("social/publish/", SocialPublishAPI.as_view(), name="social-publish"),
    path(
        "social/moderation/",
        SocialModerationAPI.as_view(),
        name="social-moderation-list",
    ),
    path(
        "social/moderation/<uuid:item_id>/",
        SocialModerationAPI.as_view(),
        name="social-moderation-action",
    ),
    path(
        "social/analytics/pulse/",
        SocialAnalyticsPulseAPI.as_view(),
        name="social-analytics-pulse",
    ),
    path(
        "social/attribution/",
        SocialAttributionAPI.as_view(),
        name="social-attribution",
    ),
    # v3.62.2 — country-adaptive signup form data (local-first wave 1).
    path(
        "localization/<str:country_code>/",
        country_localization_pack,
        name="localization-country-pack",
    ),
]
