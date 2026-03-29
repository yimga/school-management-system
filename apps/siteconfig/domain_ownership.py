"""
Ownership rules for retiring `siteconfig` as a mega-domain.

This module is intentionally lightweight and import-safe so scripts can use it
without booting Django. It classifies tenant-settings row fields and legacy config
surfaces into one target owner during the cutover.
"""

from __future__ import annotations

from typing import Final

OWNERSHIP_DOMAINS: Final[tuple[str, ...]] = (
    "safe_platform_default",
    "brand_experience",
    "runtime_blueprints",
    "policies_rules",
    "plans_entitlements",
    "global_registries",
    "metadata_governance",
    "marketplace_integrations",
    "reports",
    "documents",
    "design_studio",
    "preview_platform",
    "delete",
)

EXACT_FIELD_OWNERS: Final[dict[str, str]] = {
    "maintenance_mode": "safe_platform_default",
    "preview_mode_enabled": "preview_platform",
    "preview_note": "preview_platform",
    "custom_css": "brand_experience",
    "meta_description": "brand_experience",
    "site_name": "brand_experience",
    "tagline": "brand_experience",
    "company_name": "brand_experience",
    "company_address": "brand_experience",
    "company_phone": "brand_experience",
    "company_email": "brand_experience",
    "company_slug": "brand_experience",
    "branded_domain": "brand_experience",
    "primary_color": "brand_experience",
    "accent_color": "brand_experience",
    "success_color": "brand_experience",
    "warning_color": "brand_experience",
    "danger_color": "brand_experience",
    "header_bg_color": "brand_experience",
    "footer_bg_color": "brand_experience",
    "theme_brightness": "brand_experience",
    "theme_harmony": "brand_experience",
    "public_brand_primary_color": "brand_experience",
    "public_brand_accent_color": "brand_experience",
    "use_dark_mode": "brand_experience",
    "backend_console_theme": "brand_experience",
    "favicon": "brand_experience",
    "default_sidebar_collapsed": "brand_experience",
    "use_secondary_font_for_headings": "brand_experience",
    "admin_use_site_primary": "brand_experience",
    "social_links": "brand_experience",
    "skip_theme_publish_guard": "preview_platform",
    "backend_feature_flags": "policies_rules",
    "portal_features": "policies_rules",
    "notification_channels": "policies_rules",
    "enable_parent_portal": "policies_rules",
    "enable_teacher_portal": "policies_rules",
    "default_portal_role_dual_role": "policies_rules",
    "grade_approval_enabled": "policies_rules",
    "grade_approval_auto_validate": "policies_rules",
    "enable_concurrent_mark_uploads": "policies_rules",
    "enable_practical_assessment": "policies_rules",
    "require_mfa_roles": "policies_rules",
    "require_mfa_all_staff": "policies_rules",
    "requests_reminder_interval_hours": "policies_rules",
    "teacher_reminder_time_of_day": "policies_rules",
    "use_promotion_rule_for_pass": "policies_rules",
    "notify_parent_welcome_email": "policies_rules",
    "enable_offline_mode": "policies_rules",
    "offline_sync_conflict_resolution": "policies_rules",
    "compliance_profile_id": "policies_rules",
    "referral_bonus_amount": "policies_rules",
    "cache_rankings_interval_minutes": "safe_platform_default",
    "auto_tag_photos_from_exif": "documents",
    "admin_portal_stats_config": "runtime_blueprints",
    "default_widgets_per_role": "runtime_blueprints",
    "default_dashboard_view": "runtime_blueprints",
    "default_refresh_rate": "runtime_blueprints",
    "portal_quick_actions": "runtime_blueprints",
    "portal_announcements": "runtime_blueprints",
    "portal_recent_grades": "runtime_blueprints",
    "portal_upcoming_assessments": "runtime_blueprints",
    "top_students_default_limit": "runtime_blueprints",
    "theme_pack": "brand_experience",
    "admin_theme_pack": "brand_experience",
    "teacher_theme_pack": "brand_experience",
    "parent_theme_pack": "brand_experience",
    "country": "global_registries",
    "region": "global_registries",
    "ministry": "global_registries",
    "default_region": "global_registries",
    "default_grading_scale": "global_registries",
    "ministry_registration_code": "global_registries",
    "school_code": "runtime_blueprints",
    "admission_number_mode": "runtime_blueprints",
    "admission_number_pattern": "runtime_blueprints",
    "admission_number_strategy": "runtime_blueprints",
    "admission_number_template": "runtime_blueprints",
    "default_term_report_style": "reports",
    "default_annual_report_style": "reports",
    "default_report_preview_type": "reports",
    "enable_reports_pdf": "reports",
    "reports_require_approved_grades_before_publish": "reports",
    "reports_use_approved_grades_only": "reports",
    "report_downloads_enabled": "reports",
    "sms_provider": "marketplace_integrations",
    "ai_provider_api_key": "marketplace_integrations",
    "sms_api_key": "marketplace_integrations",
    "whatsapp_api_token": "marketplace_integrations",
    "sms_sender_id": "marketplace_integrations",
    "email_from_address": "marketplace_integrations",
    "smtp_password": "marketplace_integrations",
    "webhook_signing_secret": "marketplace_integrations",
    "marketplace_partner_client_secret": "marketplace_integrations",
    "whatsapp_support_number": "marketplace_integrations",
    "whatsapp_admissions_number": "marketplace_integrations",
    "enable_whatsapp_parent_portal": "marketplace_integrations",
    "enable_whatsapp_staff_portal": "marketplace_integrations",
    "marksheet_ocr_command": "marketplace_integrations",
    "marksheet_ocr_api_key": "marketplace_integrations",
    "updated_at": "delete",
}

PREFIX_FIELD_OWNERS: Final[tuple[tuple[str, str], ...]] = (
    ("theme_", "brand_experience"),
    ("brand_", "brand_experience"),
    ("logo_", "brand_experience"),
    ("logo", "brand_experience"),
    ("background_", "brand_experience"),
    ("video_", "brand_experience"),
    ("svg_", "brand_experience"),
    ("footer_", "brand_experience"),
    ("header_", "brand_experience"),
    ("login_", "brand_experience"),
    ("sidebar_", "brand_experience"),
    ("portal_sidebar_", "brand_experience"),
    ("show_header_", "brand_experience"),
    ("secondary_font", "brand_experience"),
    ("base_font", "brand_experience"),
    ("default_dashboard_", "runtime_blueprints"),
    ("dashboard_", "runtime_blueprints"),
    ("workflow_", "runtime_blueprints"),
    ("tour_", "preview_platform"),
    ("preview_", "preview_platform"),
    ("report_", "reports"),
    ("grading_", "global_registries"),
    ("education_", "global_registries"),
    ("holiday_", "global_registries"),
    ("weather_", "global_registries"),
    ("locale_", "global_registries"),
    ("language_", "global_registries"),
    ("currency_", "plans_entitlements"),
    ("plan_", "plans_entitlements"),
    ("billing_", "plans_entitlements"),
    ("ai_", "marketplace_integrations"),
    ("integration_", "marketplace_integrations"),
    ("webhook_", "marketplace_integrations"),
    ("api_", "marketplace_integrations"),
    ("sms_", "marketplace_integrations"),
    ("whatsapp_", "marketplace_integrations"),
    ("document_", "documents"),
    ("signature_", "documents"),
    ("design_", "design_studio"),
    ("layout_", "design_studio"),
    ("grade_", "policies_rules"),
    ("delegation_", "policies_rules"),
    ("finance_", "policies_rules"),
    ("teacher_deadline_", "policies_rules"),
    ("teacher_reminder_", "policies_rules"),
    ("notify_", "policies_rules"),
    ("syllabus_", "policies_rules"),
    ("pass_", "policies_rules"),
    ("weak_subject_", "policies_rules"),
    ("improvement_delta_", "policies_rules"),
    ("deadline_", "policies_rules"),
    ("offline_", "policies_rules"),
    ("top_students_", "runtime_blueprints"),
)


def is_runtime_payload_shadow_key(field_name: str) -> bool:
    """
    True if `field_name` is a legacy tenant-settings virtual key (stored in RuntimeDefaults.payload),
    excluding keys deleted from the ownership map.
    """
    normalized = str(field_name or "").strip()
    if not normalized or normalized.startswith("_"):
        return False
    if normalized in EXACT_FIELD_OWNERS:
        return EXACT_FIELD_OWNERS[normalized] != "delete"
    for prefix, _owner in PREFIX_FIELD_OWNERS:
        if normalized.startswith(prefix):
            return True
    if normalized.endswith("_template"):
        return True
    if normalized.endswith("_policy"):
        return True
    if normalized.endswith("_pack"):
        return True
    if normalized.endswith("_registry"):
        return True
    return False


def classify_site_settings_field(field_name: str) -> str:
    normalized = str(field_name or "").strip()
    if not normalized:
        return "delete"
    if normalized in EXACT_FIELD_OWNERS:
        return EXACT_FIELD_OWNERS[normalized]
    for prefix, owner in PREFIX_FIELD_OWNERS:
        if normalized.startswith(prefix):
            return owner
    if normalized.endswith("_template"):
        return "design_studio"
    if normalized.endswith("_policy"):
        return "policies_rules"
    if normalized.endswith("_pack"):
        return "runtime_blueprints"
    if normalized.endswith("_registry"):
        return "global_registries"
    return "metadata_governance"
