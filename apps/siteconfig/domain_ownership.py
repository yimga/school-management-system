"""
Ownership rules for retiring `siteconfig` as a mega-domain.

This module is intentionally lightweight and import-safe so scripts can use it
without booting Django. It classifies SiteSettings fields and legacy config
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
    "backend_feature_flags": "policies_rules",
    "portal_features": "policies_rules",
    "notification_channels": "policies_rules",
    "admin_portal_stats_config": "runtime_blueprints",
    "default_widgets_per_role": "runtime_blueprints",
    "default_dashboard_view": "runtime_blueprints",
    "default_refresh_rate": "runtime_blueprints",
    "portal_quick_actions": "runtime_blueprints",
    "portal_announcements": "runtime_blueprints",
    "portal_recent_grades": "runtime_blueprints",
    "portal_upcoming_assessments": "runtime_blueprints",
    "theme_pack": "brand_experience",
    "admin_theme_pack": "brand_experience",
    "teacher_theme_pack": "brand_experience",
    "parent_theme_pack": "brand_experience",
    "country": "global_registries",
    "region": "global_registries",
    "ministry": "global_registries",
    "school_code": "runtime_blueprints",
    "admission_number_mode": "runtime_blueprints",
    "admission_number_pattern": "runtime_blueprints",
    "admission_number_strategy": "runtime_blueprints",
    "admission_number_template": "runtime_blueprints",
    "sms_sender_id": "marketplace_integrations",
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
    ("document_", "documents"),
    ("signature_", "documents"),
    ("design_", "design_studio"),
    ("layout_", "design_studio"),
)


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
