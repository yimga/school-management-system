from django.urls import path
from django.shortcuts import redirect

from .views import (
    maintenance_view,
    customizer,
    clear_preview,
    preview_from_form,
    report_library,
    download_report,
    bulk_letters,
    reportcard_builder,
    reportcard_style_preview,
    reportcard_style_pdf,
    user_preferences,
    set_default_dashboard_view,
    theme_colors_page,
    theme_experience_redirect,
    toggle_preview_mode,
    set_act_as_role,
)
from .views_feature_control import (
    feature_control_panel,
    feature_control_export,
    feature_control_audit_log,
    feature_control_api,
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
    path("theme-colors/", theme_colors_page, name="theme_colors"),
    path("theme-experience/", theme_experience_redirect, name="theme_experience_redirect"),
    path("preview-from-form/", preview_from_form, name="preview_from_form"),
    path("preferences/", user_preferences, name="user_preferences"),
    path("preferences/set-default-view/", set_default_dashboard_view, name="set_default_dashboard_view"),
    path("preferences/theme/", update_theme, name="update_theme"),
    path("reports/", report_library, name="report_library"),
    path("reports/download/<slug:slug>/", download_report, name="report_download"),
    path("reports/bulk-letters/", bulk_letters, name="bulk_letters"),
    path("reports/builder/", reportcard_builder, name="reportcard_builder"),
    path("reports/preview/<slug:slug>/", reportcard_style_preview, name="reportcard_style_preview"),
    path("reports/preview/<slug:slug>/<str:report_type>/pdf/", reportcard_style_pdf, name="reportcard_style_pdf"),
    path("preview/toggle/", toggle_preview_mode, name="toggle_preview_mode"),
    path("act-as/", set_act_as_role, name="set_act_as_role"),
    path("feature-control/", feature_control_panel, name="feature_control_panel"),
    path("feature-control/export/", feature_control_export, name="feature_control_export"),
    path("feature-control/audit/", feature_control_audit_log, name="feature_control_audit"),
    path("feature-control/api/", feature_control_api, name="feature_control_api"),
]
