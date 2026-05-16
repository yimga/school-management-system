"""Mount under path('api/v2/', include(...))."""

from django.urls import path

from apps.api import views_v2

app_name = "api_v2"

urlpatterns = [
    path("ping/", views_v2.ApiV2PingView.as_view(), name="ping"),  # rbac-allow: liveness probe — no PII, no state
    path("manifest.json", views_v2.ApiV2ManifestView.as_view(), name="manifest"),  # rbac-allow: API manifest — public capability/version listing
]
