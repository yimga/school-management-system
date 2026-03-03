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
from apps.schools.marketing_views import marketing_landing, regional_marketing_landing, marketing_page, topical_marketing_landing
from apps.schools.signup_views import signup_school, verify_signup, api_trial_school, onboarding_wizard
from apps.schools.section8_views import (
    verify_caddy_domain,
    global_login_discovery,
    find_school,
    public_verify_hub,
    public_support_hub,
    lti_launch,
    lti_launch_callback,
    lti_ags_lineitems,
    lti_ags_lineitem_detail,
    lti_ags_scores,
    lti_ags_results,
    lti_nrps_memberships,
    lti_deep_linking,
    jwks_json,
    frozen_account,
)


def home(request):
    # Authenticated users go to their backend/dashboard
    if request.user.is_authenticated:
        return redirect("accounts:redirect")
    # Base/public host (runmycampus.com): public marketing landing, not login
    from apps.schools.tenant_url import is_base_domain, get_single_tenant_slug
    if is_base_domain(request):
        return redirect("marketing_landing")
    # Single tenant on non-base host: send to tenant login (subdomain only)
    slug = get_single_tenant_slug()
    if slug:
        from apps.schools.models import School
        from apps.schools.tenant_url import build_tenant_backend_url
        school = School.objects.filter(slug=slug, is_active=True).first() or School.objects.filter(subdomain__iexact=slug, is_active=True).first()
        if school:
            return redirect(build_tenant_backend_url(request, school, path="/authentication/login/"))
    return redirect("accounts:login")


def offline_page(request):
    """Offline fallback shell served by service-worker navigation fallback."""
    return render(request, "offline.html", status=200)


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


_schema_view_raw = cache_page(60)(get_schema_view(
    title="Gilead SMS API",
    description="Entity/analytics/session claims schema for frontend orchestration",
    version="1.0.0",
))


@login_required
@user_passes_test(_is_schema_allowed)
def schema_view(request):
    """API schema (JSON) – same access as schema UI."""
    return _schema_view_raw(request)


def admin_siteconfig_customizer_redirect(request):
    """Backward compatible URL.

    The customizer lives at /siteconfig/customizer/.
    Many people will naturally try /admin/siteconfig/customizer/.
    Keep it working to reduce support headaches.
    """
    return redirect('/siteconfig/customizer/')


def permission_denied(request, exception):
    """Custom 403: friendly message when staff hit Admin without superuser."""
    is_admin_forbidden = (
        request.path.startswith('/admin') and
        request.user.is_authenticated and
        request.user.is_staff and
        not request.user.is_superuser
    )
    return render(request, 'errors/403.html', {'is_admin_forbidden': is_admin_forbidden}, status=403)


def page_not_found(request, exception):
    """Custom 404 page."""
    return render(request, 'errors/404.html', status=404)


def server_error(request):
    """Custom 500 page. Pass user so base template and includes render when context processors failed."""
    context = {"user": getattr(request, "user", None)}
    return render(request, "errors/500.html", context, status=500)


handler403 = permission_denied
handler404 = page_not_found
handler500 = server_error

urlpatterns = [
    path('', home, name='home'),
    path('offline/', offline_page, name='offline'),

    # Admin interfaces - /admin/ only for superuser/staff
    path('admin/', admin_site.urls),

    # API schema (RBAC-protected; same as schema UI)
    path('api/schema/', schema_view, name='api-schema'),
    path('api/schema/ui/', api_schema_ui, name='api-schema-ui'),
    
    # Frontend admin dashboard - separate from /admin/ (redirect to canonical URL)
    path('backend/', lambda request: redirect('accounts:backend_dashboard', permanent=False)),

    # Health and metrics
    path('healthz/', obs_views.healthz, name='healthz'),
    # Public health endpoint for load balancers
    path('health/', obs_views.public_health, name='health'),
    path('ready/', obs_views.public_health, name='ready'),
    path('status/', obs_views.public_health, name='status'),
    path('metrics/', obs_views.metrics, name='metrics'),
    path('api/observability/copilot-metrics/', obs_views.copilot_metrics_json, name='copilot_metrics_json'),
    path('api/observability/slo-dashboard/', obs_views.api_operational_slo_dashboard, name='api_operational_slo_dashboard'),
    
    # Legacy alias: /admin/dashboard/ resolves to canonical /admin/
    path('admin/dashboard/', obs_views.admin_dashboard, name='admin_dashboard'),
    
    # API endpoints for admin dashboard
    path('api/health/', obs_views.api_health, name='api_health'),
    path('api/admin/weather/', obs_views.api_admin_weather, name='api_admin_weather'),
    path('api/weather/context/', obs_views.api_weather_context, name='api_weather_context'),
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
    path("verify/<str:token>/", __import__("apps.siteconfig.views_verify", fromlist=["verify_student_id"]).verify_student_id, name="verify_student_id"),
    path('api/', include(('apps.api.urls', 'api'), namespace='api')),
    path('api/v1/', include(('apps.api.urls_v1', 'api_v1'), namespace='api_v1')),

    # Apps
    path('siteconfig/', include(('apps.siteconfig.urls', 'siteconfig'), namespace='siteconfig')),
    path('api-center/', include(('apps.apicenter.urls', 'apicenter'), namespace='apicenter')),
    path('authentication/', include(('apps.accounts.urls', 'accounts'), namespace='accounts')),
    path('evals/', include(('apps.evals.urls', 'evals'), namespace='evals')),
    path('academics/', include(('apps.academics.urls', 'academics'), namespace='academics')),
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
    # Super Admin (multi-tenant provisioning)
    path('super/', include(('apps.schools.super_urls', 'super'), namespace='super')),
    # Section 8: Caddy on-demand TLS ask (no auth; restrict by IP in production)
    path('api/caddy-check/', verify_caddy_domain),
    path('api/v1/auth/check-domain/', verify_caddy_domain),
    path('discover/', global_login_discovery, name='global_login_discovery'),
    path('find/', find_school, name='find_school'),
    path('verify/', public_verify_hub, name='public_verify_hub'),
    path('support/', public_support_hub, name='public_support_hub'),
    path('marketing/', marketing_landing, name='marketing_landing'),
    path("product/", marketing_page, {"page_slug": "product"}, name="marketing_product"),
    path("solutions/", marketing_page, {"page_slug": "solutions"}, name="marketing_solutions"),
    path("pricing/", marketing_page, {"page_slug": "pricing"}, name="marketing_pricing"),
    path("compare/", marketing_page, {"page_slug": "compare"}, name="marketing_compare"),
    path("case-studies/", marketing_page, {"page_slug": "case-studies"}, name="marketing_case_studies"),
    path("security-compliance/", marketing_page, {"page_slug": "security-compliance"}, name="marketing_security_compliance"),
    path("integrations/", marketing_page, {"page_slug": "integrations"}, name="marketing_integrations"),
    path("book-demo/", marketing_page, {"page_slug": "book-demo"}, name="marketing_book_demo"),
    path("solutions/<str:topic_slug>/", topical_marketing_landing, name="marketing_topic"),
    path('cm/', regional_marketing_landing, {"country_code": "CM"}, name='marketing_cm'),
    path('ca/', regional_marketing_landing, {"country_code": "CA"}, name='marketing_ca'),
    path('onboard/', onboarding_wizard, name='onboard_wizard'),
    path('signup/', signup_school, name='signup_school'),
    path('verify-signup/', verify_signup, name='verify_signup'),
    path('api/trial/', api_trial_school, name='api_trial_school'),
    path('lti/launch/<str:tool_id>/', lti_launch, name='lti_launch'),
    path('lti/launch/<str:tool_id>/callback/', lti_launch_callback, name='lti_launch_callback'),
    path('lti/service/<str:tool_id>/lineitems', lti_ags_lineitems, name='lti_ags_lineitems'),
    path('lti/service/<str:tool_id>/lineitems/<str:lineitem_id>', lti_ags_lineitem_detail, name='lti_ags_lineitem_detail'),
    path('lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/scores', lti_ags_scores, name='lti_ags_scores'),
    path('lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/results', lti_ags_results, name='lti_ags_results'),
    path('lti/service/<str:tool_id>/memberships', lti_nrps_memberships, name='lti_nrps_memberships'),
    path('lti/service/<str:tool_id>/deep-linking', lti_deep_linking, name='lti_deep_linking'),
    path('lti/jwks.json', jwks_json, name='lti_jwks'),
    path('account-frozen/', frozen_account, name='account_frozen'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
