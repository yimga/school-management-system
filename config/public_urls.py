"""
Public (marketing + discovery) URL configuration for runmycampus.com.
Used when request.urlconf is set to this module by UrlConfSwitcherMiddleware.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render
from django.urls import include, path

from apps.observability import views as obs_views
from apps.schools.error_views import school_not_found_public
from apps.schools.marketing_views import (
    marketing_landing,
    regional_marketing_landing,
    marketing_robots_txt,
    marketing_sitemap_xml,
)
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
)
from apps.schools.signup_views import (
    signup_school,
    verify_signup,
    api_trial_school,
    onboarding_wizard,
)
from apps.siteconfig.views_verify import verify_student_id


def home(request):
    return marketing_landing(request)


def offline_page(request):
    return render(request, "offline.html", status=200)


urlpatterns = [
    path("", home, name="home"),
    path("offline/", offline_page, name="offline"),
    path("authentication/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("api/weather/context/", obs_views.api_weather_context, name="api_weather_context"),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("api/caddy-check/", verify_caddy_domain),
    path("api/v1/auth/check-domain/", verify_caddy_domain),
    path("discover/", global_login_discovery, name="global_login_discovery"),
    path("find/", find_school, name="find_school"),
    path("verify/", public_verify_hub, name="public_verify_hub"),
    path("support/", public_support_hub, name="public_support_hub"),
    path("school-not-found/", school_not_found_public, name="school_not_found_public"),
    path("marketing/", marketing_landing, name="marketing_landing"),
    path("cm/", regional_marketing_landing, {"country_code": "CM", "language_code": "fr"}, name="marketing_cm"),
    path("ca/", regional_marketing_landing, {"country_code": "CA", "language_code": "en"}, name="marketing_ca"),
    path("onboard/", onboarding_wizard, name="onboard_wizard"),
    path("signup/", signup_school, name="signup_school"),
    path("verify-signup/", verify_signup, name="verify_signup"),
    path("verify/<str:token>/", verify_student_id, name="verify_student_id"),
    path("api/trial/", api_trial_school, name="api_trial_school"),
    path("robots.txt", marketing_robots_txt, name="marketing_robots_txt"),
    path("sitemap.xml", marketing_sitemap_xml, name="marketing_sitemap_xml"),
    path("lti/launch/<str:tool_id>/", lti_launch, name="lti_launch"),
    path("lti/launch/<str:tool_id>/callback/", lti_launch_callback, name="lti_launch_callback"),
    path("lti/service/<str:tool_id>/lineitems", lti_ags_lineitems, name="lti_ags_lineitems"),
    path("lti/service/<str:tool_id>/lineitems/<str:lineitem_id>", lti_ags_lineitem_detail, name="lti_ags_lineitem_detail"),
    path("lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/scores", lti_ags_scores, name="lti_ags_scores"),
    path("lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/results", lti_ags_results, name="lti_ags_results"),
    path("lti/service/<str:tool_id>/memberships", lti_nrps_memberships, name="lti_nrps_memberships"),
    path("lti/service/<str:tool_id>/deep-linking", lti_deep_linking, name="lti_deep_linking"),
    path("lti/jwks.json", jwks_json, name="lti_jwks"),
    path("<str:language_code>/<str:country_code>/", regional_marketing_landing, name="marketing_region"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
