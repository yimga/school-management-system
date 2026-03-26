"""
First-class columns on ``RuntimeDefaults`` (platform_runtime-owned).

These keys are **not** duplicated in ``RuntimeDefaults.payload`` when present; they are
read from typed columns and override payload in ``get_effective_site_settings`` merge
order. ``sms_api_key`` stays payload-only (secret; excluded from Phase B marketplace snapshot).

See ``RuntimeDefaults.sync_from_site_settings`` and ``_build_platform_site_settings_base``.
"""

from __future__ import annotations

# Field names on RuntimeDefaults model (must match migration + model definition).
RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES: tuple[str, ...] = (
    "company_name",
    "company_email",
    "company_phone",
    "company_address",
    "company_slug",
    "country",
    "region",
    "ministry_registration_code",
    "ministry",
    "default_region",
    "default_grading_scale",
    "admission_number_mode",
    "admission_number_pattern",
    "admission_number_strategy",
    "admission_number_template",
    "admin_portal_stats_config",
    "accent_color",
    "danger_color",
    "custom_css",
    "admin_use_site_primary",
    "default_sidebar_collapsed",
    "default_dashboard_view",
    "default_refresh_rate",
    "default_widgets_per_role",
    "portal_announcements",
    "portal_quick_actions",
    "portal_recent_grades",
    "portal_upcoming_assessments",
    "top_students_default_limit",
    "site_name",
    "primary_color",
    "success_color",
    "warning_color",
    "social_links",
    "use_dark_mode",
    "use_secondary_font_for_headings",
    "default_portal_role_dual_role",
    "enable_parent_portal",
    "enable_teacher_portal",
    "backend_console_theme",
    "header_bg_color",
    "footer_bg_color",
    "theme_brightness",
    "theme_harmony",
    "grade_approval_enabled",
    "grade_approval_auto_validate",
    "enable_practical_assessment",
    "enable_concurrent_mark_uploads",
    "enable_offline_mode",
    "maintenance_mode",
    "theme_pack",
    "admin_theme_pack",
    "teacher_theme_pack",
    "parent_theme_pack",
    "default_term_report_style",
    "default_annual_report_style",
    "default_report_preview_type",
    "enable_reports_pdf",
    "reports_require_approved_grades_before_publish",
    "require_mfa_all_staff",
    "use_promotion_rule_for_pass",
    "notify_parent_welcome_email",
    "reports_use_approved_grades_only",
    "requests_reminder_interval_hours",
    "backend_feature_flags",
    "portal_features",
    "notification_channels",
    "require_mfa_roles",
    "offline_sync_conflict_resolution",
    "compliance_profile_id",
    "referral_bonus_amount",
    "tagline",
    "school_code",
    "meta_description",
    "branded_domain",
    "public_brand_primary_color",
    "public_brand_accent_color",
    "cache_rankings_interval_minutes",
    "preview_mode_enabled",
    "preview_note",
    "skip_theme_publish_guard",
    "sms_provider",
    "sms_sender_id",
    "email_from_address",
    "whatsapp_support_number",
    "whatsapp_admissions_number",
    "enable_whatsapp_parent_portal",
    "enable_whatsapp_staff_portal",
    "marksheet_ocr_command",
)

# Empty string on these means "no platform default" (do not beat RuntimeDefaults.payload).
RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "company_name",
        "company_email",
        "company_phone",
        "company_address",
        "company_slug",
        "country",
        "region",
        "ministry_registration_code",
        "ministry",
        "default_region",
        "default_grading_scale",
        "admission_number_mode",
        "admission_number_pattern",
        "admission_number_strategy",
        "admission_number_template",
        "accent_color",
        "danger_color",
        "custom_css",
        "default_dashboard_view",
        "site_name",
        "primary_color",
        "success_color",
        "warning_color",
        "default_portal_role_dual_role",
        "backend_console_theme",
        "header_bg_color",
        "footer_bg_color",
        "theme_brightness",
        "theme_harmony",
        "theme_pack",
        "admin_theme_pack",
        "teacher_theme_pack",
        "parent_theme_pack",
        "default_term_report_style",
        "default_annual_report_style",
        "default_report_preview_type",
        "offline_sync_conflict_resolution",
        "tagline",
        "school_code",
        "meta_description",
        "branded_domain",
        "public_brand_primary_color",
        "public_brand_accent_color",
        "preview_note",
        "sms_provider",
        "sms_sender_id",
        "email_from_address",
        "whatsapp_support_number",
        "whatsapp_admissions_number",
        "marksheet_ocr_command",
    }
)


def runtime_defaults_first_class_string_is_blank(val: object) -> bool:
    return isinstance(val, str) and not val.strip()


def strip_runtime_defaults_first_class_keys_from_dict(d: dict) -> None:
    """Remove first-class keys from a payload dict (in-place)."""
    for k in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES:
        d.pop(k, None)


def collect_first_class_values_from_site_settings(site_settings) -> dict[str, object]:
    """Snapshot current effective values from the legacy SiteSettings façade (virtual + column)."""
    out: dict[str, object] = {}
    for k in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES:
        v = getattr(site_settings, k, None)
        if k in RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES:
            if runtime_defaults_first_class_string_is_blank(v):
                v = None
        out[k] = v
    return out
