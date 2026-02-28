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
from apps.schools.api_views import SchoolConfigAPI
from apps.analytics.benchmark_views import BenchmarkComparisonAPI
from apps.api.offline_replay_views import OfflineReplayBatchAPI, PrefetchUrlsAPI, QueueMetricsAPI
from apps.api.sync_delta_api import DeltaSyncAPI
from apps.api.lead_capture_api import LeadCaptureAPI
from apps.api.rosetta_views import RosettaStoneConvertAPI, RosettaStoneScalesAPI
from apps.api.interop_stubs import oneroster_readiness, lti13_readiness
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
    # Scheduling (Wave 5): conflict check
    path('schedules/<int:schedule_id>/conflicts/', ScheduleConflictsAPI.as_view(), name='schedule-conflicts'),
    
    # Mobile API endpoints
    path('mobile/', include(router.urls)),

    # Phase 9: Ministry / external API placeholders (501 until implemented)
    path('ministry/cartescolaire/', cartescolaire_placeholder, name='ministry-cartescolaire'),
    path('ministry/dgi/', dgi_placeholder, name='ministry-dgi'),
    # Offline: batch replay (SW queue) and delta sync (Phase 2)
    path('offline/replay_batch/', OfflineReplayBatchAPI.as_view(), name='offline-replay-batch'),
    path('offline/delta/', DeltaSyncAPI.as_view(), name='offline-delta'),
    path('offline/prefetch_urls/', PrefetchUrlsAPI.as_view(), name='offline-prefetch-urls'),
    path('offline/queue_metrics/', QueueMetricsAPI.as_view(), name='offline-queue-metrics'),
    # ViewSet routes (notifications, devices, etc)
    path('', include(router.urls)),
]
