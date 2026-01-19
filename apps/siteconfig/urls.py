from django.urls import path
from django.shortcuts import redirect

from .views import (
    maintenance_view,
    customizer,
    clear_preview,
    report_library,
    download_report,
    user_preferences,
)

app_name = "siteconfig"

urlpatterns = [
    path("maintenance/", maintenance_view, name="maintenance"),
    # Redirect legacy customizer paths into settings
    path("customizer/", lambda request: redirect("siteconfig:user_preferences")),
    path("customizer/clear-preview/", clear_preview, name="clear_preview"),
    path("preferences/", user_preferences, name="user_preferences"),
    path("reports/", report_library, name="report_library"),
    path("reports/download/<slug:slug>/", download_report, name="report_download"),
]
