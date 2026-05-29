"""
Phase 9 Task 2 + API Integration: Mobile & Dashboard API URLs
REST endpoints for mobile applications and dashboard APIs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.api.auth_views import (
    RateLimitedTokenObtainPairView,
    RateLimitedTokenRefreshView,
)
from apps.api.mobile_api import (
    MobileDeviceViewSet,
    PushNotificationViewSet,
    OfflineSyncViewSet,
)
from apps.api.notification_api import NotificationViewSet
from apps.api.dashboard_api import (
    AdminDashboardOverviewAPI,
    TeacherDashboardAPI,
    ParentDashboardAPI,
    StudentDashboardAPI,
    FinancialDashboardAPI,
    AcademicDashboardAPI,
)
from apps.api.dashboard_layout_api import DashboardLayoutAPI
from apps.api.user_preferences_api import PortalPreferencesAPI
from apps.api.search_api import GlobalSearchAPI, SearchSuggestionsAPI
from apps.api.teacher_hover_api import TeacherHoverContextView
from apps.api.insight_anomalies_api import InsightAnomaliesAPIView
from apps.api.analytics_viz_api import AnalyticsVizOverviewAPIView
from apps.academics.api_views import AttendanceViewSet, ScheduleConflictsAPI
from apps.api.entity_api import (
    ClassroomViewSet,
    ProfileView,
    SessionClaimsView,
    StudentGuardianViewSet,
    StudentProfileViewSet,
    TeacherProfileViewSet,
    TeacherRosterView,
)
from apps.api.digital_id_api import DigitalIDAPI, DigitalIDChildrenAPI
from apps.finance.api_views import FinancialAnalyticsAPI, InvoiceViewSet, PaymentViewSet
from apps.api.ministry_placeholders import cartescolaire_placeholder, dgi_placeholder
from apps.api.government_views import GovernmentAggregatesAPI
from apps.api.config_diff_views import ConfigDiffAPI
from apps.api.roadmap_due_today_views import (
    RegionalTaxConfigAPI,
    GraphQLStubAPI,
    EdgeConfigAPI,
    TestingMatrixAPI,
    CanaryStatusAPI,
    RPO_RTOConfigAPI,
    CMSStubAPI,
    FeatureFlagsStatusAPI,
    OnboardingStatusAPI,
    SupportCopilotStubAPI,
    TenantMediaStubAPI,
    GapLedgerStatusAPI,
)
from apps.api.roadmap_extended_views import (
    CommercialSelfServeAPI,
    QuoteToContractStubAPI,
    BIAdHocReportStubAPI,
    MLRegistryStubAPI,
    ORToolsTimetablingStubAPI,
    VideoAttendanceSyncStubAPI,
    DisputePayoutFlowsStubAPI,
    UKTermPresetStubAPI,
    NestedTenancyStubAPI,
    RedisTenantCacheStubAPI,
    PredictiveEngineStubAPI,
    AtRiskDashboardStubAPI,
    ExecutiveDashboardStubAPI,
    Locale100LangStubAPI,
    CertificationBadgeExpiryStubAPI,
    NiceToHaveModulesAPI,
)
from apps.schools.api_views import SchoolConfigAPI
from apps.analytics.benchmark_views import BenchmarkComparisonAPI
from apps.api.offline_replay_views import (
    OfflineReplayBatchAPI,
    PrefetchUrlsAPI,
    QueueMetricsAPI,
)
from apps.api.sync_delta_api import DeltaSyncAPI
from apps.api.offline_device_api import OfflineTokenMintView
from apps.api.iam_offline_api import OfflineIamIntentAPI, PermissionSnapshotAPI
from apps.api.sync_bundle_api import SyncBundleUploadView
from apps.portal.views_command_bar import api_command_bar_search
from apps.portal.views_ai_line import api_ai_line_interpret
from apps.portal.views_admissions_intake import (
    api_admissions_intake_schema,
    api_admissions_applicant_scores,
)
from apps.portal.views_wedges import api_wedge_list, api_wedge_detail
from apps.api import oneroster as _oneroster
from apps.api import oneroster_csv_importer as _oneroster_csv
from apps.api import oneroster_writes as _oneroster_writes
from apps.api import oneroster_results as _oneroster_results
from apps.portal.views_ai_product import (
    api_smart_settings_assistant,
    api_import_error_resolver,
    api_guardrail_report_generator,
    api_guided_tour_planner,
)
from apps.portal.views_ai_gateway import (
    api_setup_assistant,
    api_workflow_draft,
    api_policy_explain,
    api_document_classify,
    api_semantic_search,
    api_migration_suggest,
    api_admin_copilot,
    api_theme_recommend,
    api_feature_control_explain,
    api_report_recommend,
    api_design_studio_draft,
    api_live_preview_explain,
    api_system_config_explain,
    api_dashboard_pack_recommend,
    api_support_assistant,
    api_support_assistant_stream,
    api_tenant_maturity,
    api_data_quality_assistant,
    api_marketplace_recommend,
    api_control_plane_intelligence,
    api_ai_feedback,
    api_support_session_rating,
    api_interop_assistant,
    api_runtime_config_explain,
    api_observability_assistant,
    api_billing_usage_explain,
    api_trust_compliance_assistant,
    api_studio_os_assistant,
)
from apps.portal.views_workflow_playbook import (
    api_offboarding_playbook_ask,
    api_onboarding_playbook_ask,
)
from apps.portal.views_mcp_product import api_mcp_invoke_tool, api_mcp_list_tools
from apps.portal.views_support_deflection import (
    api_support_deflection,
    api_support_deflection_ack,
)
from apps.portal.views_kb_typeahead import api_kb_typeahead
from apps.api.lead_capture_api import LeadCaptureAPI
from apps.api.rosetta_views import RosettaStoneConvertAPI, RosettaStoneScalesAPI
from apps.api.interop_stubs import (
    oneroster_readiness,
    lti13_readiness,
    edfi_readiness,
    ceds_readiness,
    district_readiness_sample,
    interop_hub,
)
from apps.api.edfi_views import (
    edfi_students,
    edfi_student_school_associations,
    edfi_grades,
)
from apps.api.ceds_views import ceds_students, ceds_enrollments, ceds_grades
from apps.api.scim_views import (
    scim_service_provider_config,
    scim_users,
    scim_user_detail,
    scim_groups,
    scim_group_detail,
)
from apps.api.learning_institution_api import (
    IdentityGraphSummaryView,
    InstitutionProfileSuggestView,
    LearningPackInstallView,
    LearningPackRollbackView,
    LearningWedgeBenchmarksView,
    MinistryStubPdfView,
    StatutoryExtractJsonView,
    TerminologyPackView,
)
from apps.api.br_northstar_views import (
    ClimateReportingHooksView,
    ComplianceValidateAttendanceView,
    ComplianceValidateEnrollmentView,
    DemographicInsightsView,
    EWSListCreateView,
    LegacySisReadonlyStubView,
    MessagingRetentionPolicyView,
    MigrationDiffPreviewView,
    NLAdminGovernedQueryView,
    SLOTargetsAPIView,
    TenantRegistriesEffectiveView,
)
from apps.api.control_plane_internal_views import ControlPlaneBridgeManifestAPIView
from apps.api.oneroster_roster_webhook import (
    oneroster_roster_webhook,
    platform_marketplace_integration_webhook,
)
from apps.api.north_star_api_views import (
    NorthStarEventCatalogView,
    NorthStarPackageImpactView,
    NorthStarRumWebVitalsSummaryView,
    NorthStarUpcomingDeadlinesView,
    NorthStarWedgePlaybookView,
)
from apps.api.oneroster_views import (
    manifest as oneroster_manifest,
    academic_sessions as oneroster_academic_sessions,
    classes as oneroster_classes,
    students as oneroster_students,
    teachers as oneroster_teachers,
    enrollments as oneroster_enrollments,
    orgs as oneroster_orgs,
    courses as oneroster_courses,
    users as oneroster_users,
)

router = DefaultRouter()
router.register(r"devices", MobileDeviceViewSet, basename="mobile-device")
router.register(
    r"push-notifications", PushNotificationViewSet, basename="push-notification"
)
router.register(r"sync", OfflineSyncViewSet, basename="offline-sync")
router.register(r"attendance", AttendanceViewSet, basename="attendance")
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"entities/students", StudentProfileViewSet, basename="entity-student")
router.register(r"entities/teachers", TeacherProfileViewSet, basename="entity-teacher")
router.register(
    r"entities/guardians", StudentGuardianViewSet, basename="entity-guardian"
)
router.register(r"entities/classrooms", ClassroomViewSet, basename="entity-classroom")
router.register(r"finance/invoices", InvoiceViewSet, basename="finance-invoice")
router.register(r"finance/payments", PaymentViewSet, basename="finance-payment")

urlpatterns = [
    # School branding config (multi-tenant; from request host)
    path("config/", SchoolConfigAPI.as_view(), name="config"),
    # Benchmark comparison (Phase 4)
    path(
        "benchmark/comparison/",
        BenchmarkComparisonAPI.as_view(),
        name="benchmark-comparison",
    ),
    path(
        "learning/pack-install/",
        LearningPackInstallView.as_view(),
        name="api-learning-pack-install",
    ),
    path(
        "learning/pack-rollback/",
        LearningPackRollbackView.as_view(),
        name="api-learning-pack-rollback",
    ),
    path(
        "learning/institution-suggest/",
        InstitutionProfileSuggestView.as_view(),
        name="api-institution-suggest",
    ),
    path(  # rbac-allow: public terminology pack — read-only, no PII
        "learning/terminology/",
        TerminologyPackView.as_view(),
        name="api-learning-terminology",
    ),
    path(
        "learning/ministry-pdf/",
        MinistryStubPdfView.as_view(),
        name="api-ministry-stub-pdf",
    ),
    path(
        "learning/statutory-extract/",
        StatutoryExtractJsonView.as_view(),
        name="api-statutory-extract-json",
    ),
    path(
        "learning/identity-graph-summary/",
        IdentityGraphSummaryView.as_view(),
        name="api-identity-graph-summary",
    ),
    path(
        "internal/learning-wedge-benchmarks/",
        LearningWedgeBenchmarksView.as_view(),
        name="api-learning-wedge-benchmarks",
    ),
    # JWT Authentication
    path(  # rbac-allow: token-issuance endpoint — auth happens via credentials in body, rate-limited
        "auth/token/",
        RateLimitedTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(  # rbac-allow: token-refresh endpoint — auth via refresh-token in body, rate-limited
        "auth/token/refresh/",
        RateLimitedTokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path("auth/profile/", ProfileView.as_view(), name="auth-profile"),
    path("session/claims/", SessionClaimsView.as_view(), name="session-claims"),
    path(
        "entities/teacher-roster/", TeacherRosterView.as_view(), name="teacher-roster"
    ),
    # Dashboard Overview APIs
    path(
        "dashboard/admin/", AdminDashboardOverviewAPI.as_view(), name="admin-dashboard"
    ),
    path("dashboard/teacher/", TeacherDashboardAPI.as_view(), name="teacher-dashboard"),
    path("dashboard/parent/", ParentDashboardAPI.as_view(), name="parent-dashboard"),
    path("dashboard/student/", StudentDashboardAPI.as_view(), name="student-dashboard"),
    path(
        "dashboard/financial/",
        FinancialDashboardAPI.as_view(),
        name="financial-dashboard",
    ),
    path(
        "dashboard/academic/", AcademicDashboardAPI.as_view(), name="academic-dashboard"
    ),
    path(
        "finance/analytics/", FinancialAnalyticsAPI.as_view(), name="finance-analytics"
    ),
    path(
        "dashboard/layout/<str:page>/",
        DashboardLayoutAPI.as_view(),
        name="dashboard-layout",
    ),
    path(
        "portal-preferences/", PortalPreferencesAPI.as_view(), name="portal-preferences"
    ),
    # Phase 5: Admissions CRM — Lead Capture (public POST by school_slug)
    path("admissions/lead/", LeadCaptureAPI.as_view(), name="lead-capture"),  # rbac-allow: public lead-capture from marketing forms — school_slug in body, rate-limited
    # Interoperability hub (B6: first-class product surface) + per-standard endpoints
    path("interop/", interop_hub, name="interop-hub"),
    path("interop/oneroster/", oneroster_readiness, name="interop-oneroster"),
    path("interop/lti13/", lti13_readiness, name="interop-lti13"),
    path("interop/edfi/students/", edfi_students, name="interop-edfi-students"),  # rbac-allow: middleware-api-key-auth (Ed-Fi standard B2B)
    path(  # rbac-allow: middleware-api-key-auth (Ed-Fi standard B2B)
        "interop/edfi/studentSchoolAssociations/",
        edfi_student_school_associations,
        name="interop-edfi-associations",
    ),
    path("interop/edfi/grades/", edfi_grades, name="interop-edfi-grades"),  # rbac-allow: middleware-api-key-auth (Ed-Fi standard B2B)
    path("interop/edfi/", edfi_readiness, name="interop-edfi"),
    path("interop/ceds/students/", ceds_students, name="interop-ceds-students"),  # rbac-allow: middleware-api-key-auth (CEDS standard B2B)
    path(  # rbac-allow: middleware-api-key-auth (CEDS standard B2B)
        "interop/ceds/enrollments/", ceds_enrollments, name="interop-ceds-enrollments"
    ),
    path("interop/ceds/grades/", ceds_grades, name="interop-ceds-grades"),  # rbac-allow: middleware-api-key-auth (CEDS standard B2B)
    path("interop/ceds/", ceds_readiness, name="interop-ceds"),
    path(
        "interop/district-readiness/sample/",
        district_readiness_sample,
        name="interop-district-readiness-sample",
    ),
    # SCIM 2.0 baseline (tenant-scoped provisioning)
    path(  # rbac-allow: SCIM standard — bearer-token auth via middleware (RFC 7644)
        "scim/v2/ServiceProviderConfig",
        scim_service_provider_config,
        name="scim-service-provider-config",
    ),
    path("scim/v2/Users", scim_users, name="scim-users"),  # rbac-allow: SCIM bearer-token middleware-auth
    path("scim/v2/Users/<str:user_id>", scim_user_detail, name="scim-user-detail"),  # rbac-allow: SCIM bearer-token middleware-auth
    path("scim/v2/Groups", scim_groups, name="scim-groups"),  # rbac-allow: SCIM bearer-token middleware-auth
    path("scim/v2/Groups/<str:group_id>", scim_group_detail, name="scim-group-detail"),  # rbac-allow: SCIM bearer-token middleware-auth
    # OneRoster 1.1 baseline roster exchange
    path("oneroster/v1p1/manifest", oneroster_manifest, name="oneroster-manifest"),  # rbac-allow: OneRoster bearer-token middleware-auth
    path(  # rbac-allow: OneRoster bearer-token middleware-auth
        "oneroster/v1p1/academicSessions",
        oneroster_academic_sessions,
        name="oneroster-academic-sessions",
    ),
    path("oneroster/v1p1/classes", oneroster_classes, name="oneroster-classes"),  # rbac-allow: OneRoster bearer-token middleware-auth
    path("oneroster/v1p1/students", oneroster_students, name="oneroster-students"),  # rbac-allow: OneRoster bearer-token middleware-auth
    path("oneroster/v1p1/teachers", oneroster_teachers, name="oneroster-teachers"),  # rbac-allow: OneRoster bearer-token middleware-auth
    path(  # rbac-allow: OneRoster bearer-token middleware-auth
        "oneroster/v1p1/enrollments",
        oneroster_enrollments,
        name="oneroster-enrollments",
    ),
    path("oneroster/v1p1/orgs", oneroster_orgs, name="oneroster-orgs"),  # rbac-allow: OneRoster bearer-token middleware-auth
    path("oneroster/v1p1/courses", oneroster_courses, name="oneroster-courses"),  # rbac-allow: OneRoster bearer-token middleware-auth
    path("oneroster/v1p1/users", oneroster_users, name="oneroster-users"),  # rbac-allow: OneRoster bearer-token middleware-auth
    path(
        "oneroster/v1p1/roster-webhook",
        oneroster_roster_webhook,
        name="oneroster-roster-webhook",
    ),
    path(
        "integrations/v1/platform-webhook",
        platform_marketplace_integration_webhook,
        name="platform-marketplace-integration-webhook",
    ),
    # Phase 5: Digital ID for wallet / partner apps
    path("portal/digital-id/", DigitalIDAPI.as_view(), name="digital-id"),
    path(
        "portal/digital-id/children/",
        DigitalIDChildrenAPI.as_view(),
        name="digital-id-children",
    ),
    # Rosetta Stone: cross-tenant / cross-system grade conversion
    path("rosetta/convert/", RosettaStoneConvertAPI.as_view(), name="rosetta-convert"),
    path("rosetta/scales/", RosettaStoneScalesAPI.as_view(), name="rosetta-scales"),
    # Search APIs
    path("search/", GlobalSearchAPI.as_view(), name="global-search"),
    path(
        "search/suggestions/", SearchSuggestionsAPI.as_view(), name="search-suggestions"
    ),
    path(
        "internal/teacher-hover/",
        TeacherHoverContextView.as_view(),
        name="api-teacher-hover",
    ),
    path(
        "internal/insight-anomalies/",
        InsightAnomaliesAPIView.as_view(),
        name="api-insight-anomalies",
    ),
    path(
        "internal/analytics-viz/overview/",
        AnalyticsVizOverviewAPIView.as_view(),
        name="api-analytics-viz-overview",
    ),
    path(
        "internal/br/slo-targets/",
        SLOTargetsAPIView.as_view(),
        name="api-br-slo-targets",
    ),
    path(
        "internal/control-plane/bridge-manifest/",
        ControlPlaneBridgeManifestAPIView.as_view(),
        name="api-control-plane-bridge-manifest",
    ),
    path(
        "internal/br/compliance/validate-enrollment/",
        ComplianceValidateEnrollmentView.as_view(),
        name="api-br-validate-enrollment",
    ),
    path(
        "internal/br/compliance/validate-attendance/",
        ComplianceValidateAttendanceView.as_view(),
        name="api-br-validate-attendance",
    ),
    path(
        "internal/br/migration-diff-preview/",
        MigrationDiffPreviewView.as_view(),
        name="api-br-migration-diff",
    ),
    path("internal/br/ews/", EWSListCreateView.as_view(), name="api-br-ews"),
    path(
        "internal/br/nl-admin-query/",
        NLAdminGovernedQueryView.as_view(),
        name="api-br-nl-admin",
    ),
    path(
        "internal/br/messaging-retention/",
        MessagingRetentionPolicyView.as_view(),
        name="api-br-messaging-retention",
    ),
    path(
        "internal/br/legacy-sis-readonly/",
        LegacySisReadonlyStubView.as_view(),
        name="api-br-legacy-sis",
    ),
    path(
        "internal/br/tenant-registries-effective/",
        TenantRegistriesEffectiveView.as_view(),
        name="api-br-tenant-registries",
    ),
    path(
        "internal/br/demographic-insights/",
        DemographicInsightsView.as_view(),
        name="api-br-demographic-insights",
    ),
    path(
        "internal/br/climate-reporting-hooks/",
        ClimateReportingHooksView.as_view(),
        name="api-br-climate-hooks",
    ),
    path(
        "internal/north-star/event-catalog/",
        NorthStarEventCatalogView.as_view(),
        name="api-north-star-event-catalog",
    ),
    path(
        "internal/north-star/wedge-playbook/",
        NorthStarWedgePlaybookView.as_view(),
        name="api-north-star-wedge-playbook",
    ),
    path(
        "internal/north-star/package-impact/",
        NorthStarPackageImpactView.as_view(),
        name="api-north-star-package-impact",
    ),
    path(
        "internal/north-star/rum-web-vitals/",
        NorthStarRumWebVitalsSummaryView.as_view(),
        name="api-north-star-rum-web-vitals",
    ),
    path(
        "internal/north-star/upcoming-deadlines/",
        NorthStarUpcomingDeadlinesView.as_view(),
        name="api-north-star-upcoming-deadlines",
    ),
    # AI Gateway productized endpoints (RunMyCampus blueprint; all via backend gateway)
    path("ai/setup-assistant/", api_setup_assistant, name="ai-setup-assistant"),
    path("ai/workflow-draft/", api_workflow_draft, name="ai-workflow-draft"),
    path("ai/policy-explain/", api_policy_explain, name="ai-policy-explain"),
    path("ai/document-classify/", api_document_classify, name="ai-document-classify"),
    path("ai/semantic-search/", api_semantic_search, name="ai-semantic-search"),
    path("ai/migration-suggest/", api_migration_suggest, name="ai-migration-suggest"),
    path("ai/admin-copilot/", api_admin_copilot, name="ai-admin-copilot"),
    path("ai/theme-recommend/", api_theme_recommend, name="ai-theme-recommend"),
    path(
        "ai/feature-control-explain/",
        api_feature_control_explain,
        name="ai-feature-control-explain",
    ),
    path("ai/report-recommend/", api_report_recommend, name="ai-report-recommend"),
    path(
        "ai/design-studio-draft/",
        api_design_studio_draft,
        name="ai-design-studio-draft",
    ),
    path(
        "ai/live-preview-explain/",
        api_live_preview_explain,
        name="ai-live-preview-explain",
    ),
    path(
        "ai/system-config-explain/",
        api_system_config_explain,
        name="ai-system-config-explain",
    ),
    path(
        "ai/dashboard-pack-recommend/",
        api_dashboard_pack_recommend,
        name="ai-dashboard-pack-recommend",
    ),
    path("ai/support-assistant/", api_support_assistant, name="ai-support-assistant"),
    path(
        "ai/support-assistant/stream/",
        api_support_assistant_stream,
        name="ai-support-assistant-stream",
    ),
    path("support/deflection/", api_support_deflection, name="support-deflection"),
    path(
        "support/deflection/ack/",
        api_support_deflection_ack,
        name="support-deflection-ack",
    ),
    path("kb/typeahead/", api_kb_typeahead, name="kb-typeahead"),
    path("ai/command-bar/", api_command_bar_search, name="ai-command-bar"),
    path("ai/line-interpret/", api_ai_line_interpret, name="ai-line-interpret"),
    path("admissions/intake-schema/", api_admissions_intake_schema, name="admissions-intake-schema"),
    path("admissions/applicant-scores/", api_admissions_applicant_scores, name="admissions-applicant-scores"),
    # v4.00.35: wedge registry JSON API
    path("super/wedges/", api_wedge_list, name="super-wedge-list"),
    path("super/wedges/<int:wedge_id>/", api_wedge_detail, name="super-wedge-detail"),
    # v4.00.36: OneRoster v1.2 read-only Rostering endpoints (wedge 44)
    path("roster/v1p2/orgs/", _oneroster.orgs, name="api-roster-v1p2-orgs"),
    path("roster/v1p2/schools/", _oneroster.schools, name="api-roster-v1p2-schools"),
    path("roster/v1p2/users/", _oneroster.users, name="api-roster-v1p2-users"),
    path("roster/v1p2/students/", _oneroster.students, name="api-roster-v1p2-students"),
    path("roster/v1p2/teachers/", _oneroster.teachers, name="api-roster-v1p2-teachers"),
    path("roster/v1p2/classes/", _oneroster.classes, name="api-roster-v1p2-classes"),
    path("roster/v1p2/academic-sessions/", _oneroster.academic_sessions, name="api-roster-v1p2-academic-sessions"),
    # v4.00.38: OneRoster v1.2 CSV bundle import (Clever/ClassLink-compatible)
    path("roster/v1p2/import/", _oneroster_csv.import_bundle, name="api-roster-v1p2-import"),
    path("roster/v1p2/import/last-report/", _oneroster_csv.last_import_report, name="api-roster-v1p2-import-last-report"),
    # v4.00.38: OneRoster v1.2 PUT (single-entity upsert) with idempotency-key
    path("roster/v1p2/orgs/<str:sourced_id>/", _oneroster_writes.put_org, name="api-roster-v1p2-put-org"),
    path("roster/v1p2/users/<str:sourced_id>/", _oneroster_writes.put_user, name="api-roster-v1p2-put-user"),
    path("roster/v1p2/classes/<str:sourced_id>/", _oneroster_writes.put_class, name="api-roster-v1p2-put-class"),
    # v4.00.39: OneRoster Result Service (read-only line items + results)
    path("roster/results/v1p2/lineItems/", _oneroster_results.line_items_list, name="api-roster-results-line-items"),
    path("roster/results/v1p2/lineItems/<str:sourced_id>/", _oneroster_results.line_item_detail, name="api-roster-results-line-item-detail"),
    path("roster/results/v1p2/results/", _oneroster_results.results_collection, name="api-roster-results-list"),
    path("roster/results/v1p2/results/<str:sourced_id>/", _oneroster_results.result_detail, name="api-roster-results-detail"),
    # v4.00.41: OneRoster Result Service WRITE (grade pass-back, idempotent PUT)
    path("roster/results/v1p2/results/<str:sourced_id>/put/", _oneroster_results.put_result, name="api-roster-results-put"),
    # v4.00.42: POST creates a fresh result row; DELETE soft-removes it.
    path("roster/results/v1p2/results/post/", _oneroster_results.post_result, name="api-roster-results-post"),
    path("roster/results/v1p2/results/<str:sourced_id>/delete/", _oneroster_results.delete_result, name="api-roster-results-delete"),
    # v4.00.48: LineItem write coverage (POST + PUT + DELETE).
    path("roster/results/v1p2/lineItems/post/", _oneroster_results.post_line_item, name="api-roster-results-line-item-post"),
    path("roster/results/v1p2/lineItems/<str:sourced_id>/put/", _oneroster_results.put_line_item, name="api-roster-results-line-item-put"),
    path("roster/results/v1p2/lineItems/<str:sourced_id>/delete/", _oneroster_results.delete_line_item, name="api-roster-results-line-item-delete"),
    # v4.00.47: GradingPeriods + Categories (OneRoster Result Service spec coverage).
    path("roster/results/v1p2/gradingPeriods/", _oneroster_results.grading_periods_collection, name="api-roster-results-grading-periods"),
    path("roster/results/v1p2/gradingPeriods/<str:sourced_id>/", _oneroster_results.grading_period_dispatch, name="api-roster-results-grading-period-detail"),
    # v4.00.52: GradingPeriod write coverage (POST + PUT + DELETE).
    path("roster/results/v1p2/gradingPeriods/post/", _oneroster_results.post_grading_period, name="api-roster-results-grading-period-post"),
    path("roster/results/v1p2/gradingPeriods/<str:sourced_id>/put/", _oneroster_results.put_grading_period, name="api-roster-results-grading-period-put"),
    path("roster/results/v1p2/gradingPeriods/<str:sourced_id>/delete/", _oneroster_results.delete_grading_period, name="api-roster-results-grading-period-delete"),
    path("roster/results/v1p2/categories/", _oneroster_results.categories_collection, name="api-roster-results-categories"),
    # v4.00.53: Category write coverage (POST + PUT + DELETE) — POST route
    # registered BEFORE the ``<str:sourced_id>`` catch-all so ``post`` is not
    # parsed as a sourcedId.
    path("roster/results/v1p2/categories/post/", _oneroster_results.post_category, name="api-roster-results-category-post"),
    path("roster/results/v1p2/categories/<str:sourced_id>/put/", _oneroster_results.put_category, name="api-roster-results-category-put"),
    path("roster/results/v1p2/categories/<str:sourced_id>/delete/", _oneroster_results.delete_category, name="api-roster-results-category-delete"),
    path("roster/results/v1p2/categories/<str:sourced_id>/", _oneroster_results.category_dispatch, name="api-roster-results-category-detail"),
    path(
        "ai/smart-settings/",
        api_smart_settings_assistant,
        name="ai-smart-settings",
    ),
    path(
        "ai/import-error-resolver/",
        api_import_error_resolver,
        name="ai-import-error-resolver",
    ),
    path(
        "ai/guardrail-report/",
        api_guardrail_report_generator,
        name="ai-guardrail-report",
    ),
    path(
        "ai/guided-tour/",
        api_guided_tour_planner,
        name="ai-guided-tour",
    ),
    path("ai/tenant-maturity/", api_tenant_maturity, name="ai-tenant-maturity"),
    path(
        "ai/data-quality-assistant/",
        api_data_quality_assistant,
        name="ai-data-quality-assistant",
    ),
    path(
        "ai/marketplace-recommend/",
        api_marketplace_recommend,
        name="ai-marketplace-recommend",
    ),
    path(
        "ai/control-plane-intelligence/",
        api_control_plane_intelligence,
        name="ai-control-plane-intelligence",
    ),
    path("ai/interop-assistant/", api_interop_assistant, name="ai-interop-assistant"),
    path(
        "ai/runtime-config-explain/",
        api_runtime_config_explain,
        name="ai-runtime-config-explain",
    ),
    path(
        "ai/observability-assistant/",
        api_observability_assistant,
        name="ai-observability-assistant",
    ),
    path(
        "ai/billing-usage-explain/",
        api_billing_usage_explain,
        name="ai-billing-usage-explain",
    ),
    path(
        "ai/trust-compliance-assistant/",
        api_trust_compliance_assistant,
        name="ai-trust-compliance-assistant",
    ),
    path(
        "ai/studio-os-assistant/",
        api_studio_os_assistant,
        name="ai-studio-os-assistant",
    ),
    path(
        "ai/onboarding-playbook/",
        api_onboarding_playbook_ask,
        name="ai-onboarding-playbook",
    ),
    path(
        "ai/offboarding-playbook/",
        api_offboarding_playbook_ask,
        name="ai-offboarding-playbook",
    ),
    path("ai/mcp/tools/", api_mcp_list_tools, name="ai-mcp-list-tools"),
    path("ai/mcp/invoke/", api_mcp_invoke_tool, name="ai-mcp-invoke"),
    path("ai/feedback/", api_ai_feedback, name="ai-feedback"),
    path(
        "ai/support-session-rating/",
        api_support_session_rating,
        name="ai-support-session-rating",
    ),
    # Scheduling (Wave 5): conflict check
    path(
        "schedules/<int:schedule_id>/conflicts/",
        ScheduleConflictsAPI.as_view(),
        name="schedule-conflicts",
    ),
    # Mobile API endpoints
    path("mobile/", include(router.urls)),
    # Phase 9: Ministry / external API placeholders (501 until implemented)
    path(
        "ministry/cartescolaire/",
        cartescolaire_placeholder,
        name="ministry-cartescolaire",
    ),
    path("ministry/dgi/", dgi_placeholder, name="ministry-dgi"),
    # Government / district aggregates (14.5) — permission-gated, no PII
    path(
        "government/aggregates/",
        GovernmentAggregatesAPI.as_view(),
        name="government-aggregates",
    ),
    # Config diff (29.4) — compare policy between schools or current vs staged
    path("config-diff/", ConfigDiffAPI.as_view(), name="config-diff"),
    # Offline: batch replay (SW queue) and delta sync (Phase 2)
    path(
        "offline/replay_batch/",
        OfflineReplayBatchAPI.as_view(),
        name="offline-replay-batch",
    ),
    path("offline/delta/", DeltaSyncAPI.as_view(), name="offline-delta"),
    path(
        "offline/prefetch_urls/",
        PrefetchUrlsAPI.as_view(),
        name="offline-prefetch-urls",
    ),
    path(
        "offline/queue_metrics/",
        QueueMetricsAPI.as_view(),
        name="offline-queue-metrics",
    ),
    path(
        "devices/offline-token/",
        OfflineTokenMintView.as_view(),
        name="devices-offline-token",
    ),
    path(
        "offline/permission_snapshot/",
        PermissionSnapshotAPI.as_view(),
        name="offline-permission-snapshot",
    ),
    path(
        "offline/iam_intent/",
        OfflineIamIntentAPI.as_view(),
        name="offline-iam-intent",
    ),
    path(
        "sync/bundle/upload/",
        SyncBundleUploadView.as_view(),
        name="sync-bundle-upload",
    ),
    # Roadmap due-today implementations (ROADMAP_DUE_TODAY.md) — 16.x, 17.x, 29.x, 30/31, section_11, TENANT_MEDIA, gap ledger
    path(
        "roadmap/regional-tax/",
        RegionalTaxConfigAPI.as_view(),
        name="roadmap-regional-tax",
    ),
    path("roadmap/graphql/", GraphQLStubAPI.as_view(), name="roadmap-graphql"),
    path("roadmap/edge/", EdgeConfigAPI.as_view(), name="roadmap-edge"),
    path(
        "roadmap/testing-matrix/",
        TestingMatrixAPI.as_view(),
        name="roadmap-testing-matrix",
    ),
    path("roadmap/canary/", CanaryStatusAPI.as_view(), name="roadmap-canary"),
    path("roadmap/rpo-rto/", RPO_RTOConfigAPI.as_view(), name="roadmap-rpo-rto"),
    path("roadmap/cms/", CMSStubAPI.as_view(), name="roadmap-cms"),
    path(
        "roadmap/feature-flags/",
        FeatureFlagsStatusAPI.as_view(),
        name="roadmap-feature-flags",
    ),
    path(
        "roadmap/onboarding/", OnboardingStatusAPI.as_view(), name="roadmap-onboarding"
    ),
    path(
        "roadmap/support-copilot/",
        SupportCopilotStubAPI.as_view(),
        name="roadmap-support-copilot",
    ),
    path(
        "roadmap/tenant-media/",
        TenantMediaStubAPI.as_view(),
        name="roadmap-tenant-media",
    ),
    path(
        "roadmap/gap-ledger/", GapLedgerStatusAPI.as_view(), name="roadmap-gap-ledger"
    ),
    # Extended roadmap (REFINEMENT, Phase 9, RUNMYCAMPUS_ROADMAP_TASKS, nice-to-have) — apps/api/roadmap_extended_views.py
    path(
        "roadmap/commercial-self-serve/",
        CommercialSelfServeAPI.as_view(),
        name="roadmap-commercial-self-serve",
    ),
    path(
        "roadmap/quote-to-contract/",
        QuoteToContractStubAPI.as_view(),
        name="roadmap-quote-to-contract",
    ),
    path(
        "roadmap/bi-ad-hoc/", BIAdHocReportStubAPI.as_view(), name="roadmap-bi-ad-hoc"
    ),
    path(
        "roadmap/ml-registry/", MLRegistryStubAPI.as_view(), name="roadmap-ml-registry"
    ),
    path(
        "roadmap/or-tools-timetabling/",
        ORToolsTimetablingStubAPI.as_view(),
        name="roadmap-or-tools-timetabling",
    ),
    path(
        "roadmap/video-attendance-sync/",
        VideoAttendanceSyncStubAPI.as_view(),
        name="roadmap-video-attendance-sync",
    ),
    path(
        "roadmap/dispute-payout/",
        DisputePayoutFlowsStubAPI.as_view(),
        name="roadmap-dispute-payout",
    ),
    path(
        "roadmap/uk-term-preset/",
        UKTermPresetStubAPI.as_view(),
        name="roadmap-uk-term-preset",
    ),
    path(
        "roadmap/nested-tenancy/",
        NestedTenancyStubAPI.as_view(),
        name="roadmap-nested-tenancy",
    ),
    path(
        "roadmap/redis-tenant-cache/",
        RedisTenantCacheStubAPI.as_view(),
        name="roadmap-redis-tenant-cache",
    ),
    path(
        "roadmap/predictive-engine/",
        PredictiveEngineStubAPI.as_view(),
        name="roadmap-predictive-engine",
    ),
    path(
        "roadmap/at-risk-dashboard/",
        AtRiskDashboardStubAPI.as_view(),
        name="roadmap-at-risk-dashboard",
    ),
    path(
        "roadmap/executive-dashboard/",
        ExecutiveDashboardStubAPI.as_view(),
        name="roadmap-executive-dashboard",
    ),
    path(
        "roadmap/locale-100-lang/",
        Locale100LangStubAPI.as_view(),
        name="roadmap-locale-100-lang",
    ),
    path(
        "roadmap/certification-badge-expiry/",
        CertificationBadgeExpiryStubAPI.as_view(),
        name="roadmap-certification-badge-expiry",
    ),
    path(
        "roadmap/nice-to-have-modules/",
        NiceToHaveModulesAPI.as_view(),
        name="roadmap-nice-to-have-modules",
    ),
    # ViewSet routes (notifications, devices, etc)
    path("", include(router.urls)),
]
