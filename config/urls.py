from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path, reverse
from django.views.decorators.cache import cache_page
from rest_framework.schemas import get_schema_view
from django.contrib.auth.decorators import login_required, user_passes_test
from django.template.response import TemplateResponse
from django.http import HttpResponseForbidden

from apps.siteconfig.models import SiteSettings

from apps.observability import views as obs_views
from apps.portal.views_ai_copilot import (
    ai_copilot_query,
    ai_permissions,
    ai_copilot_limits,
    ai_copilot_config,
    ai_copilot_audit_feed,
)
from config.admin import admin_site


def home(request):
    # Redirect based on role/authentication status
    if request.user.is_authenticated:
        return redirect("accounts:redirect")
    # Everyone else goes to login
    return redirect("accounts:login")


def _is_schema_allowed(user):
    role = (getattr(user, "role", "") or "").upper()
    return user.is_authenticated and (user.is_staff or user.is_superuser or role in {"ADMIN", "IT_ADMIN", "LEADERSHIP"})


@login_required
@user_passes_test(_is_schema_allowed)
def api_schema_ui(request):
    """Render Redoc/Swagger-lite page for API schema (admin-only)."""
    flags = getattr(SiteSettings.get_solo(), "backend_feature_flags", {}) or {}
    allowed_roles = [str(r).upper() for r in flags.get("allowed_roles_api_schema", [])]
    if not flags.get("enable_api_schema_ui", True):
        return HttpResponseForbidden("API schema UI disabled by admin.")
    if allowed_roles:
        role = (getattr(request.user, "role", "") or "").upper()
        if role not in allowed_roles and not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("You are not allowed to access API schema UI.")
    return TemplateResponse(
        request,
        "api_schema_ui.html",
        {
            "schema_url": reverse("api-schema"),
        },
    )


def admin_siteconfig_customizer_redirect(request):
    """Backward compatible URL.

    The customizer lives at /siteconfig/customizer/.
    Many people will naturally try /admin/siteconfig/customizer/.
    Keep it working to reduce support headaches.
    """
    return redirect('/siteconfig/customizer/')


urlpatterns = [
    path('', home, name='home'),

    # Admin interfaces - /admin/ only for superuser/staff
    path('admin/', admin_site.urls),

    # API schema (RBAC-protected)
    path(
        'api/schema/',
        cache_page(60)(get_schema_view(
            title="Gilead SMS API",
            description="Entity/analytics/session claims schema for frontend orchestration",
            version="1.0.0"
        )),
        name='api-schema'
    ),
    path('api/schema/ui/', api_schema_ui, name='api-schema-ui'),
    
    # Frontend admin dashboard - separate from /admin/
    path('backend/', lambda request: redirect('/authentication/backend/', permanent=False)),

    # Health and metrics
    path('healthz/', obs_views.healthz, name='healthz'),
    # Public health endpoint for load balancers
    path('health/', obs_views.public_health, name='health'),
    path('metrics/', obs_views.metrics, name='metrics'),
    path('api/observability/copilot-metrics/', obs_views.copilot_metrics_json, name='copilot_metrics_json'),
    
    # Admin Dashboard (Backend-focused)
    path('admin/dashboard/', obs_views.admin_dashboard, name='admin_dashboard'),
    
    # API endpoints for admin dashboard
    path('api/health/', obs_views.api_health, name='api_health'),
    path('api/notifications/', obs_views.api_notifications, name='api_notifications'),
    path('api/notifications/mark-all-read/', obs_views.api_notifications_mark_all_read, name='api_notifications_mark_all_read'),
    
    # Phase 3 API endpoints
    path('api/activities/', obs_views.api_activities, name='api_activities'),
    path('api/dashboard/charts/', obs_views.api_dashboard_charts, name='api_dashboard_charts'),
    
    # AI Copilot API endpoints (RBAC Protected)
    path('api/ai-copilot/validate/', ai_copilot_query, name='ai_copilot_query'),
    path('api/ai-copilot/permissions/', ai_permissions, name='ai_permissions'),
    path('api/ai-copilot/limits/', ai_copilot_limits, name='ai_copilot_limits'),
    path('api/ai-copilot/config/', ai_copilot_config, name='ai_copilot_config'),
    path('api/ai-copilot/audit/', ai_copilot_audit_feed, name='ai_copilot_audit'),

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
    path('communication/', include(('apps.communication.urls', 'communication'), namespace='communication')),
    path('emis/', include(('emis.urls', 'emis'), namespace='emis')),
    path('requests/', include(('apps.requests.urls', 'requests'), namespace='requests')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
