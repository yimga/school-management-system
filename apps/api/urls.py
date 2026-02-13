"""
Phase 9 Task 2 + API Integration: Mobile & Dashboard API URLs
REST endpoints for mobile applications and dashboard APIs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
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
from apps.academics.api_views import AttendanceViewSet
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
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
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
    # Phase 5: Digital ID for wallet / partner apps
    path('portal/digital-id/', DigitalIDAPI.as_view(), name='digital-id'),
    path('portal/digital-id/children/', DigitalIDChildrenAPI.as_view(), name='digital-id-children'),

    # Search APIs
    path('search/', GlobalSearchAPI.as_view(), name='global-search'),
    path('search/suggestions/', SearchSuggestionsAPI.as_view(), name='search-suggestions'),
    
    # Mobile API endpoints
    path('mobile/', include(router.urls)),

    # Phase 9: Ministry / external API placeholders (501 until implemented)
    path('ministry/cartescolaire/', cartescolaire_placeholder, name='ministry-cartescolaire'),
    path('ministry/dgi/', dgi_placeholder, name='ministry-dgi'),
    
    # ViewSet routes (notifications, devices, etc)
    path('', include(router.urls)),
]
