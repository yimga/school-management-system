"""
Public (marketing) URL configuration for runyourcampus.com base domain.
Used when request.urlconf is set to this module by UrlConfSwitcherMiddleware.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path

from apps.observability import views as obs_views
from apps.schools.marketing_views import marketing_landing
from apps.schools.signup_views import signup_school, verify_signup, api_trial_school
from apps.schools.section8_views import (
    verify_caddy_domain,
    global_login_discovery,
    find_school,
    lti_launch,
    lti_launch_callback,
    lti_ags_lineitems,
    lti_ags_lineitem_detail,
    lti_ags_scores,
    lti_ags_results,
    lti_nrps_memberships,
    lti_deep_linking,
    jwks_json,
)
from config.admin import admin_site


def home(request):
    if request.user.is_authenticated:
        return redirect("accounts:redirect")
    return redirect("marketing_landing")


def offline_page(request):
    return render(request, "offline.html", status=200)


urlpatterns = [
    path("", home, name="home"),
    path("offline/", offline_page, name="offline"),
    path("admin/", admin_site.urls),
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    path("authentication/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("siteconfig/", include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig")),
    path("api/weather/context/", obs_views.api_weather_context, name="api_weather_context"),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("api/caddy-check/", verify_caddy_domain),
    path("api/v1/auth/check-domain/", verify_caddy_domain),
    path("discover/", global_login_discovery, name="global_login_discovery"),
    path("find/", find_school, name="find_school"),
    path("marketing/", marketing_landing, name="marketing_landing"),
    path("signup/", signup_school, name="signup_school"),
    path("verify-signup/", verify_signup, name="verify_signup"),
    path("api/trial/", api_trial_school, name="api_trial_school"),
    path("lti/launch/<str:tool_id>/", lti_launch, name="lti_launch"),
    path("lti/launch/<str:tool_id>/callback/", lti_launch_callback, name="lti_launch_callback"),
    path("lti/service/<str:tool_id>/lineitems", lti_ags_lineitems, name="lti_ags_lineitems"),
    path("lti/service/<str:tool_id>/lineitems/<str:lineitem_id>", lti_ags_lineitem_detail, name="lti_ags_lineitem_detail"),
    path("lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/scores", lti_ags_scores, name="lti_ags_scores"),
    path("lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/results", lti_ags_results, name="lti_ags_results"),
    path("lti/service/<str:tool_id>/memberships", lti_nrps_memberships, name="lti_nrps_memberships"),
    path("lti/service/<str:tool_id>/deep-linking", lti_deep_linking, name="lti_deep_linking"),
    path("lti/jwks.json", jwks_json, name="lti_jwks"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
