"""
RunMyCampus Standards Compliance: API v1 URL contract.
Mount under path('api/v1/', include('apps.api.urls_v1')).
"""

from django.urls import path
from apps.api import views_v1, views_v1_intervention, views_v1_platform
from apps.api.api_v1_manifest import api_v1_manifest
from apps.api.views_webhook_catalog import WebhookEventTypesView

app_name = "api_v1"

urlpatterns = [
    path("manifest.json", api_v1_manifest, name="manifest"),
    # Pass 12: public webhook event-type catalog backed by apps.events.catalog.
    path(
        "webhooks/event-types/",
        WebhookEventTypesView.as_view(),
        name="webhooks-event-types",
    ),
    path(
        "platform/integration-context/",
        views_v1_platform.IntegrationContextView.as_view(),
        name="platform-integration-context",
    ),
    path(
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
    path(
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
    path(
        "finance/generate-batch",
        views_v1.FinanceGenerateBatchView.as_view(),
        name="finance-generate-batch",
    ),
    path(
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
    path(
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
    path(
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
    path(
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
    path(
        "reports/scheduled",
        views_v1.ScheduledReportsListView.as_view(),
        name="reports-scheduled-list",
    ),
    path(
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
]
