from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path

from apps.observability import views as obs_views
from config.admin import admin_site


def home(request):
    # Staff/admin users: go straight to backend dashboard; everyone else to portal login
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('/backend/')
        return redirect('/portal/')
    return redirect('/authentication/login/')


def admin_siteconfig_customizer_redirect(request):
    """Backward compatible URL.

    The customizer lives at /siteconfig/customizer/.
    Many people will naturally try /admin/siteconfig/customizer/.
    Keep it working to reduce support headaches.
    """
    return redirect('/siteconfig/customizer/')


def old_backend_redirect(request):
    """Redirect from old /authentication/backend/ to new /backend/ URL."""
    return redirect('/backend/', permanent=True)


urlpatterns = [
    path('', home, name='home'),

    # Admin interfaces
    path('admin/', admin_site.urls),
    path('backend/', include(('apps.accounts.urls_backend', 'backend'), namespace='backend')),
    
    # Backward compatibility redirect
    path('authentication/backend/', old_backend_redirect),
    path('authentication/backend-dashboard/', old_backend_redirect),

    # Health and metrics
    path('healthz/', obs_views.healthz, name='healthz'),
    path('metrics/', obs_views.metrics, name='metrics'),

    # Back-compat shortcut
    path('admin/siteconfig/customizer/', admin_siteconfig_customizer_redirect),

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
