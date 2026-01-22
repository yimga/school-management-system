"""
Phase 9 Task 2: Mobile API URL Configuration
REST endpoints for mobile applications
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.api.mobile_api import (
    MobileDeviceViewSet,
    PushNotificationViewSet,
    OfflineSyncViewSet
)

router = DefaultRouter()
router.register(r'devices', MobileDeviceViewSet, basename='mobile-device')
router.register(r'notifications', PushNotificationViewSet, basename='push-notification')
router.register(r'sync', OfflineSyncViewSet, basename='offline-sync')

urlpatterns = [
    # JWT Authentication
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Mobile API endpoints
    path('mobile/', include(router.urls)),
]
