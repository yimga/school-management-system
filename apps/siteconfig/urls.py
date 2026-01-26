from django.urls import path
from django.shortcuts import redirect

from .views import (
    maintenance_view,
    customizer,
    clear_preview,
    report_library,
    download_report,
    reportcard_builder,
    reportcard_style_preview,
    reportcard_style_pdf,
    user_preferences,
    toggle_preview_mode,
    set_act_as_role,
)
from .dashboard_views import (
    update_theme,
)

app_name = "siteconfig"

urlpatterns = [
    path("maintenance/", maintenance_view, name="maintenance"),
    # Redirect legacy customizer paths into settings (keep name for templates)
    path("customizer/", customizer, name="customizer"),
    path("customizer/clear-preview/", clear_preview, name="clear_preview"),
    path("preferences/", user_preferences, name="user_preferences"),
    path("preferences/theme/", update_theme, name="update_theme"),
    path("reports/", report_library, name="report_library"),
    path("reports/download/<slug:slug>/", download_report, name="report_download"),
    path("reports/builder/", reportcard_builder, name="reportcard_builder"),
    path("reports/preview/<slug:slug>/", reportcard_style_preview, name="reportcard_style_preview"),
    path("reports/preview/<slug:slug>/<str:report_type>/pdf/", reportcard_style_pdf, name="reportcard_style_pdf"),
    path("preview/toggle/", toggle_preview_mode, name="toggle_preview_mode"),
    path("act-as/", set_act_as_role, name="set_act_as_role"),
]
