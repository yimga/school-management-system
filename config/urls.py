from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path

from apps.observability import views as obs_views
from config.admin import admin_site


def home(request):
    # Redirect based on role/authentication status
    if request.user.is_authenticated:
        # Only admin/superuser go to backend admin
        if request.user.is_staff or request.user.is_superuser:
            return redirect('/admin/')
        # Teachers and staff go to teacher portal
        if getattr(request.user, "role", None) == "TEACHER":
            return redirect('/portal/teacher/')
        # Parents go to parent portal
        if getattr(request.user, "role", None) == "PARENT":
            return redirect('/portal/parent/')
    # Everyone else goes to login
    return redirect('/authentication/login/')


def admin_siteconfig_customizer_redirect(request):
    """Backward compatible URL.

    The customizer lives at /siteconfig/customizer/.
    Many people will naturally try /admin/siteconfig/customizer/.
    Keep it working to reduce support headaches.
    """
    return redirect('/siteconfig/customizer/')


def old_backend_redirect(request):
    """Redirect from old /authentication/backend/ to new /admin/ URL."""
    return redirect('/admin/', permanent=True)


urlpatterns = [
    path('', home, name='home'),

    # Admin interfaces - /admin/ only for superuser/staff
    path('admin/', admin_site.urls),
    
    # Backward compatibility redirects
    path('backend/', lambda request: redirect('/authentication/login/', permanent=True)),
    path('authentication/backend/', old_backend_redirect),
    path('authentication/backend-dashboard/', old_backend_redirect),

    # Health and metrics
    path('healthz/', obs_views.healthz, name='healthz'),
    path('metrics/', obs_views.metrics, name='metrics'),
    
    # Admin Dashboard (Backend-focused)
    path('admin/dashboard/', obs_views.admin_dashboard, name='admin_dashboard'),
    
    # API endpoints for admin dashboard
    path('api/health/', obs_views.api_health, name='api_health'),
    path('api/notifications/', obs_views.api_notifications, name='api_notifications'),
    path('api/notifications/mark-all-read/', obs_views.api_notifications_mark_all_read, name='api_notifications_mark_all_read'),
    
    # Phase 3 API endpoints
    path('api/activities/', obs_views.api_activities, name='api_activities'),
    path('api/dashboard/charts/', obs_views.api_dashboard_charts, name='api_dashboard_charts'),

    # Back-compat shortcut
    path('admin/siteconfig/customizer/', admin_siteconfig_customizer_redirect),

    # API Routes
    path('api/', include(('apps.api.urls', 'api'), namespace='api')),

    # Apps
    path('siteconfig/', include(('apps.siteconfig.urls', 'siteconfig'), namespace='siteconfig')),
    path('authentication/', include(('apps.accounts.urls', 'accounts'), namespace='accounts')),
    path('evals/', include(('apps.evals.urls', 'evals'), namespace='evals')),
    path('portal/', include(('apps.portal.urls', 'portal'), namespace='portal')),
    path('portal', lambda request: redirect('portal:parent_dashboard')),
    path('kb/', include(('apps.portal.urls_kb', 'kb'), namespace='kb')),
    path('reports/', include(('apps.reports.urls', 'reports'), namespace='reports')),
    path('analytics/', include(('apps.analytics.urls', 'analytics'), namespace='analytics')),
    path('finance/', include(('apps.finance.urls', 'finance'), namespace='finance')),
    path('payroll/', include(('apps.payroll.urls', 'payroll'), namespace='payroll')),
    path('compliance/', include(('apps.compliance.urls', 'compliance'), namespace='compliance')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
