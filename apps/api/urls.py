"""
Phase 9 Task 2 + API Integration: Mobile & Dashboard API URLs
REST endpoints for mobile applications and dashboard APIs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.api.auth_views import RateLimitedTokenObtainPairView, RateLimitedTokenRefreshView
from apps.api.mobile_api import (
    MobileDeviceViewSet,
    PushNotificationViewSet,
    OfflineSyncViewSet
)
from apps.api.notification_api import NotificationViewSet
from apps.api.dashboard_api import (
    AdminDashboardOverviewAPI,
    TeacherDashboardAPI,
    ParentDashboardAPI,
    StudentDashboardAPI,
    FinancialDashboardAPI,
    AcademicDashboardAPI
)
from apps.api.dashboard_layout_api import DashboardLayoutAPI
from apps.api.user_preferences_api import PortalPreferencesAPI
from apps.api.search_api import GlobalSearchAPI, SearchSuggestionsAPI
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
from apps.api.offline_replay_views import OfflineReplayBatchAPI, PrefetchUrlsAPI, QueueMetricsAPI
from apps.api.sync_delta_api import DeltaSyncAPI
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
    api_tenant_maturity,
    api_data_quality_assistant,
    api_marketplace_recommend,
    api_control_plane_intelligence,
)
from apps.api.lead_capture_api import LeadCaptureAPI
from apps.api.rosetta_views import RosettaStoneConvertAPI, RosettaStoneScalesAPI
from apps.api.interop_stubs import oneroster_readiness, lti13_readiness, edfi_readiness, ceds_readiness
from apps.api.edfi_views import edfi_students, edfi_student_school_associations, edfi_grades
from apps.api.ceds_views import ceds_students, ceds_enrollments, ceds_grades
from apps.api.scim_views import (
    scim_service_provider_config,
    scim_users,
    scim_user_detail,
    scim_groups,
    scim_group_detail,
)
from apps.api.oneroster_views import (
    manifest as oneroster_manifest,
    classes as oneroster_classes,
    students as oneroster_students,
    teachers as oneroster_teachers,
    enrollments as oneroster_enrollments,
)

router = DefaultRouter()
router.register(r'devices', MobileDeviceViewSet, basename='mobile-device')
router.register(r'push-notifications', PushNotificationViewSet, basename='push-notification')
router.register(r'sync', OfflineSyncViewSet, basename='offline-sync')
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'entities/students', StudentProfileViewSet, basename='entity-student')
router.register(r'entities/teachers', TeacherProfileViewSet, basename='entity-teacher')
router.register(r'entities/guardians', StudentGuardianViewSet, basename='entity-guardian')
router.register(r'entities/classrooms', ClassroomViewSet, basename='entity-classroom')
router.register(r'finance/invoices', InvoiceViewSet, basename='finance-invoice')
router.register(r'finance/payments', PaymentViewSet, basename='finance-payment')

urlpatterns = [
    # School branding config (multi-tenant; from request host)
    path('config/', SchoolConfigAPI.as_view(), name='config'),
    # Benchmark comparison (Phase 4)
    path('benchmark/comparison/', BenchmarkComparisonAPI.as_view(), name='benchmark-comparison'),
    # JWT Authentication
    path('auth/token/', RateLimitedTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', RateLimitedTokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile/', ProfileView.as_view(), name='auth-profile'),
    path('session/claims/', SessionClaimsView.as_view(), name='session-claims'),
    path('entities/teacher-roster/', TeacherRosterView.as_view(), name='teacher-roster'),
    
    # Dashboard Overview APIs
    path('dashboard/admin/', AdminDashboardOverviewAPI.as_view(), name='admin-dashboard'),
    path('dashboard/teacher/', TeacherDashboardAPI.as_view(), name='teacher-dashboard'),
    path('dashboard/parent/', ParentDashboardAPI.as_view(), name='parent-dashboard'),
    path('dashboard/student/', StudentDashboardAPI.as_view(), name='student-dashboard'),
    path('dashboard/financial/', FinancialDashboardAPI.as_view(), name='financial-dashboard'),
    path('dashboard/academic/', AcademicDashboardAPI.as_view(), name='academic-dashboard'),
    path('finance/analytics/', FinancialAnalyticsAPI.as_view(), name='finance-analytics'),
    path('dashboard/layout/<str:page>/', DashboardLayoutAPI.as_view(), name='dashboard-layout'),
    path('portal-preferences/', PortalPreferencesAPI.as_view(), name='portal-preferences'),
    # Phase 5: Admissions CRM — Lead Capture (public POST by school_slug)
    path('admissions/lead/', LeadCaptureAPI.as_view(), name='lead-capture'),
    # Interoperability stubs (OneRoster, LTI 1.3) — implement per official specs
    path('interop/oneroster/', oneroster_readiness, name='interop-oneroster'),
    path('interop/lti13/', lti13_readiness, name='interop-lti13'),
    path('interop/edfi/students/', edfi_students, name='interop-edfi-students'),
    path('interop/edfi/studentSchoolAssociations/', edfi_student_school_associations, name='interop-edfi-associations'),
    path('interop/edfi/grades/', edfi_grades, name='interop-edfi-grades'),
    path('interop/edfi/', edfi_readiness, name='interop-edfi'),
    path('interop/ceds/students/', ceds_students, name='interop-ceds-students'),
    path('interop/ceds/enrollments/', ceds_enrollments, name='interop-ceds-enrollments'),
    path('interop/ceds/grades/', ceds_grades, name='interop-ceds-grades'),
    path('interop/ceds/', ceds_readiness, name='interop-ceds'),
    # SCIM 2.0 baseline (tenant-scoped provisioning)
    path('scim/v2/ServiceProviderConfig', scim_service_provider_config, name='scim-service-provider-config'),
    path('scim/v2/Users', scim_users, name='scim-users'),
    path('scim/v2/Users/<str:user_id>', scim_user_detail, name='scim-user-detail'),
    path('scim/v2/Groups', scim_groups, name='scim-groups'),
    path('scim/v2/Groups/<str:group_id>', scim_group_detail, name='scim-group-detail'),
    # OneRoster 1.1 baseline roster exchange
    path('oneroster/v1p1/manifest', oneroster_manifest, name='oneroster-manifest'),
    path('oneroster/v1p1/classes', oneroster_classes, name='oneroster-classes'),
    path('oneroster/v1p1/students', oneroster_students, name='oneroster-students'),
    path('oneroster/v1p1/teachers', oneroster_teachers, name='oneroster-teachers'),
    path('oneroster/v1p1/enrollments', oneroster_enrollments, name='oneroster-enrollments'),
    # Phase 5: Digital ID for wallet / partner apps
    path('portal/digital-id/', DigitalIDAPI.as_view(), name='digital-id'),
    path('portal/digital-id/children/', DigitalIDChildrenAPI.as_view(), name='digital-id-children'),

    # Rosetta Stone: cross-tenant / cross-system grade conversion
    path('rosetta/convert/', RosettaStoneConvertAPI.as_view(), name='rosetta-convert'),
    path('rosetta/scales/', RosettaStoneScalesAPI.as_view(), name='rosetta-scales'),
    # Search APIs
    path('search/', GlobalSearchAPI.as_view(), name='global-search'),
    path('search/suggestions/', SearchSuggestionsAPI.as_view(), name='search-suggestions'),
    # AI Gateway productized endpoints (RunMyCampus blueprint; all via backend gateway)
    path('ai/setup-assistant/', api_setup_assistant, name='ai-setup-assistant'),
    path('ai/workflow-draft/', api_workflow_draft, name='ai-workflow-draft'),
    path('ai/policy-explain/', api_policy_explain, name='ai-policy-explain'),
    path('ai/document-classify/', api_document_classify, name='ai-document-classify'),
    path('ai/semantic-search/', api_semantic_search, name='ai-semantic-search'),
    path('ai/migration-suggest/', api_migration_suggest, name='ai-migration-suggest'),
    path('ai/admin-copilot/', api_admin_copilot, name='ai-admin-copilot'),
    path('ai/theme-recommend/', api_theme_recommend, name='ai-theme-recommend'),
    path('ai/feature-control-explain/', api_feature_control_explain, name='ai-feature-control-explain'),
    path('ai/report-recommend/', api_report_recommend, name='ai-report-recommend'),
    path('ai/design-studio-draft/', api_design_studio_draft, name='ai-design-studio-draft'),
    path('ai/live-preview-explain/', api_live_preview_explain, name='ai-live-preview-explain'),
    path('ai/system-config-explain/', api_system_config_explain, name='ai-system-config-explain'),
    path('ai/dashboard-pack-recommend/', api_dashboard_pack_recommend, name='ai-dashboard-pack-recommend'),
    path('ai/support-assistant/', api_support_assistant, name='ai-support-assistant'),
    path('ai/tenant-maturity/', api_tenant_maturity, name='ai-tenant-maturity'),
    path('ai/data-quality-assistant/', api_data_quality_assistant, name='ai-data-quality-assistant'),
    path('ai/marketplace-recommend/', api_marketplace_recommend, name='ai-marketplace-recommend'),
    path('ai/control-plane-intelligence/', api_control_plane_intelligence, name='ai-control-plane-intelligence'),
    # Scheduling (Wave 5): conflict check
    path('schedules/<int:schedule_id>/conflicts/', ScheduleConflictsAPI.as_view(), name='schedule-conflicts'),
    
    # Mobile API endpoints
    path('mobile/', include(router.urls)),

    # Phase 9: Ministry / external API placeholders (501 until implemented)
    path('ministry/cartescolaire/', cartescolaire_placeholder, name='ministry-cartescolaire'),
    path('ministry/dgi/', dgi_placeholder, name='ministry-dgi'),
    # Government / district aggregates (14.5) — permission-gated, no PII
    path('government/aggregates/', GovernmentAggregatesAPI.as_view(), name='government-aggregates'),
    # Config diff (29.4) — compare policy between schools or current vs staged
    path('config-diff/', ConfigDiffAPI.as_view(), name='config-diff'),
    # Offline: batch replay (SW queue) and delta sync (Phase 2)
    path('offline/replay_batch/', OfflineReplayBatchAPI.as_view(), name='offline-replay-batch'),
    path('offline/delta/', DeltaSyncAPI.as_view(), name='offline-delta'),
    path('offline/prefetch_urls/', PrefetchUrlsAPI.as_view(), name='offline-prefetch-urls'),
    path('offline/queue_metrics/', QueueMetricsAPI.as_view(), name='offline-queue-metrics'),
    # Roadmap due-today implementations (ROADMAP_DUE_TODAY.md) — 16.x, 17.x, 29.x, 30/31, section_11, TENANT_MEDIA, gap ledger
    path('roadmap/regional-tax/', RegionalTaxConfigAPI.as_view(), name='roadmap-regional-tax'),
    path('roadmap/graphql/', GraphQLStubAPI.as_view(), name='roadmap-graphql'),
    path('roadmap/edge/', EdgeConfigAPI.as_view(), name='roadmap-edge'),
    path('roadmap/testing-matrix/', TestingMatrixAPI.as_view(), name='roadmap-testing-matrix'),
    path('roadmap/canary/', CanaryStatusAPI.as_view(), name='roadmap-canary'),
    path('roadmap/rpo-rto/', RPO_RTOConfigAPI.as_view(), name='roadmap-rpo-rto'),
    path('roadmap/cms/', CMSStubAPI.as_view(), name='roadmap-cms'),
    path('roadmap/feature-flags/', FeatureFlagsStatusAPI.as_view(), name='roadmap-feature-flags'),
    path('roadmap/onboarding/', OnboardingStatusAPI.as_view(), name='roadmap-onboarding'),
    path('roadmap/support-copilot/', SupportCopilotStubAPI.as_view(), name='roadmap-support-copilot'),
    path('roadmap/tenant-media/', TenantMediaStubAPI.as_view(), name='roadmap-tenant-media'),
    path('roadmap/gap-ledger/', GapLedgerStatusAPI.as_view(), name='roadmap-gap-ledger'),
    # Extended roadmap (REFINEMENT, Phase 9, RUNMYCAMPUS_ROADMAP_TASKS, nice-to-have) — apps/api/roadmap_extended_views.py
    path('roadmap/commercial-self-serve/', CommercialSelfServeAPI.as_view(), name='roadmap-commercial-self-serve'),
    path('roadmap/quote-to-contract/', QuoteToContractStubAPI.as_view(), name='roadmap-quote-to-contract'),
    path('roadmap/bi-ad-hoc/', BIAdHocReportStubAPI.as_view(), name='roadmap-bi-ad-hoc'),
    path('roadmap/ml-registry/', MLRegistryStubAPI.as_view(), name='roadmap-ml-registry'),
    path('roadmap/or-tools-timetabling/', ORToolsTimetablingStubAPI.as_view(), name='roadmap-or-tools-timetabling'),
    path('roadmap/video-attendance-sync/', VideoAttendanceSyncStubAPI.as_view(), name='roadmap-video-attendance-sync'),
    path('roadmap/dispute-payout/', DisputePayoutFlowsStubAPI.as_view(), name='roadmap-dispute-payout'),
    path('roadmap/uk-term-preset/', UKTermPresetStubAPI.as_view(), name='roadmap-uk-term-preset'),
    path('roadmap/nested-tenancy/', NestedTenancyStubAPI.as_view(), name='roadmap-nested-tenancy'),
    path('roadmap/redis-tenant-cache/', RedisTenantCacheStubAPI.as_view(), name='roadmap-redis-tenant-cache'),
    path('roadmap/predictive-engine/', PredictiveEngineStubAPI.as_view(), name='roadmap-predictive-engine'),
    path('roadmap/at-risk-dashboard/', AtRiskDashboardStubAPI.as_view(), name='roadmap-at-risk-dashboard'),
    path('roadmap/executive-dashboard/', ExecutiveDashboardStubAPI.as_view(), name='roadmap-executive-dashboard'),
    path('roadmap/locale-100-lang/', Locale100LangStubAPI.as_view(), name='roadmap-locale-100-lang'),
    path('roadmap/certification-badge-expiry/', CertificationBadgeExpiryStubAPI.as_view(), name='roadmap-certification-badge-expiry'),
    path('roadmap/nice-to-have-modules/', NiceToHaveModulesAPI.as_view(), name='roadmap-nice-to-have-modules'),
    # ViewSet routes (notifications, devices, etc)
    path('', include(router.urls)),
]
