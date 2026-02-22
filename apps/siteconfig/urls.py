from django.urls import path
from django.shortcuts import redirect

from .views import (
    branding_api,
    maintenance_view,
    customizer,
    grading_settings,
    module_market,
    clear_preview,
    preview_from_form,
    report_library,
    download_report,
    bulk_letters,
    reportcard_builder,
    reportcard_style_preview,
    reportcard_style_embed_preview,
    reportcard_style_live_preview,
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
    feature_control_weather_cities,
)
from .dashboard_views import (
    update_theme,
)
from .views_waiver import request_waiver
from .views_custom_requirement import request_custom_requirement
from .views_sync_center import sync_center, sync_center_resolve
from .views_school_theme import school_theme_settings
from .views_tag_manager import tag_manager, tag_manager_edit

app_name = "siteconfig"

urlpatterns = [
    path("maintenance/", maintenance_view, name="maintenance"),
    # Redirect legacy customizer paths into settings (keep name for templates)
    path("customizer/", customizer, name="customizer"),
    path("grading-settings/", grading_settings, name="grading_settings"),
    path("modules/", module_market, name="module_market"),
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
    path("reports/embed-preview/<slug:slug>/<str:report_type>/", reportcard_style_embed_preview, name="reportcard_style_embed_preview"),
    path("reports/live-preview/<slug:slug>/<str:report_type>/", reportcard_style_live_preview, name="reportcard_style_live_preview"),
    path("reports/preview/<slug:slug>/<str:report_type>/pdf/", reportcard_style_pdf, name="reportcard_style_pdf"),
    path("preview/toggle/", toggle_preview_mode, name="toggle_preview_mode"),
    path("act-as/", set_act_as_role, name="set_act_as_role"),
    path("feature-control/", feature_control_panel, name="feature_control_panel"),
    path("feature-control/export/", feature_control_export, name="feature_control_export"),
    path("feature-control/audit/", feature_control_audit_log, name="feature_control_audit"),
    path("feature-control/api/", feature_control_api, name="feature_control_api"),
    path("feature-control/weather-cities/", feature_control_weather_cities, name="feature_control_weather_cities"),
    path("request-waiver/", request_waiver, name="request_waiver"),
    path("request-custom-requirement/", request_custom_requirement, name="request_custom_requirement"),
    path("sync-center/", sync_center, name="sync_center"),
    path("sync-center/resolve/<int:conflict_id>/", sync_center_resolve, name="sync_center_resolve"),
    path("school-theme/", school_theme_settings, name="school_theme_settings"),
    path("tag-manager/", tag_manager, name="tag_manager"),
    path("tag-manager/<int:tag_id>/", tag_manager_edit, name="tag_manager_edit"),
    path("api/branding/", branding_api, name="branding_api"),
]
