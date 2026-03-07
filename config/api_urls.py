"""
API host URL configuration (api.runmycampus.com).
"""
from django.http import JsonResponse
from django.urls import include, path

from apps.observability import views as obs_views


def api_home(_request):
    return JsonResponse(
        {
            "service": "runmycampus-api",
            "status": "ok",
        }
    )


urlpatterns = [
    path("", api_home, name="api_home"),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path("api/", include(("apps.api.urls", "api"), namespace="api")),
    path("api/v1/", include(("apps.api.urls_v1", "api_v1"), namespace="api_v1")),
]
