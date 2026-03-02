"""
Manager host URL configuration (manager.runmycampus.com).
Dedicated for super-admin and operations access.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path

from apps.observability import views as obs_views
from config.admin import admin_site


def manager_home(request):
    if request.user.is_authenticated:
        return redirect("super:dashboard")
    return redirect("accounts:login")


def offline_page(request):
    return render(request, "offline.html", status=200)


urlpatterns = [
    path("", manager_home, name="home"),
    path("", manager_home, name="manager_home"),
    path("offline/", offline_page, name="offline"),
    path("admin/", admin_site.urls),
    path("authentication/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    path("siteconfig/", include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig")),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_health, name="status"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path("api/weather/context/", obs_views.api_weather_context, name="api_weather_context"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
