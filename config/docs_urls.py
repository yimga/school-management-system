"""
Docs host URL configuration (docs.runmycampus.com).
"""
from django.shortcuts import redirect, render
from django.urls import include, path

from apps.observability import views as obs_views


def docs_home(request):
    return render(request, "schools/docs_landing.html", {})


urlpatterns = [
    path("", docs_home, name="home"),
    path("", docs_home, name="docs_home"),
    path("authentication/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("api/weather/context/", obs_views.api_weather_context, name="api_weather_context"),
    path("<path:_unused>", lambda _request, _unused: redirect("docs_home"), name="docs_fallback"),
]
