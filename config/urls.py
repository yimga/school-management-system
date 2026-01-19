from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path


def home(request):
    # Staff/admin users: go straight to admin
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('/admin/')
        return redirect('/portal/')
    return render(request, 'home.html')


def admin_siteconfig_customizer_redirect(request):
    """Backward compatible URL.

    The customizer lives at /siteconfig/customizer/.
    Many people will naturally try /admin/siteconfig/customizer/.
    Keep it working to reduce support headaches.
    """
    return redirect('/siteconfig/customizer/')


urlpatterns = [
    path('', home, name='home'),

    path('admin/', admin.site.urls),

    # Back-compat shortcut
    path('admin/siteconfig/customizer/', admin_siteconfig_customizer_redirect),

    # Apps
    path('siteconfig/', include('apps.siteconfig.urls')),
    path('authentication/', include('apps.accounts.urls')),
    path('evals/', include('apps.evals.urls')),
    path('portal/', include('apps.portal.urls')),
    path('reports/', include('apps.reports.urls')),
    path('analytics/', include('apps.analytics.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
