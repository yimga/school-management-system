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
from apps.api.dashboard_layout_api import DashboardLayoutAPI, AvailableWidgetsAPI
from apps.api.user_preferences_api import PortalPreferencesAPI
from apps.api.search_api import GlobalSearchAPI, SearchSuggestionsAPI
from apps.api.entity_api import (
    ClassroomViewSet,
    ProfileView,
    SessionClaimsView,
    StudentGuardianViewSet,
    StudentProfileViewSet,
    TeacherProfileViewSet,
    TeacherRosterView,
)

router = DefaultRouter()
router.register(r'devices', MobileDeviceViewSet, basename='mobile-device')
router.register(r'push-notifications', PushNotificationViewSet, basename='push-notification')
router.register(r'sync', OfflineSyncViewSet, basename='offline-sync')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'entities/students', StudentProfileViewSet, basename='entity-student')
router.register(r'entities/teachers', TeacherProfileViewSet, basename='entity-teacher')
router.register(r'entities/guardians', StudentGuardianViewSet, basename='entity-guardian')
router.register(r'entities/classrooms', ClassroomViewSet, basename='entity-classroom')

urlpatterns = [
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
    path('dashboard/layout/<str:page>/', DashboardLayoutAPI.as_view(), name='dashboard-layout'),
    path('portal-preferences/', PortalPreferencesAPI.as_view(), name='portal-preferences'),
    
    # Search APIs
    path('search/', GlobalSearchAPI.as_view(), name='global-search'),
    path('search/suggestions/', SearchSuggestionsAPI.as_view(), name='search-suggestions'),
    
    # Mobile API endpoints
    path('mobile/', include(router.urls)),
    
    # ViewSet routes (notifications, devices, etc)
    path('', include(router.urls)),
]
