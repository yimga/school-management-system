from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.apps import apps as django_apps
from django.conf import settings
from django.db.models.fields.files import FieldFile

from apps.accounts.models import User


PORTAL_FEATURE_OPTIONS: list[tuple[str, str]] = [
    ("messaging", "Messaging"),
    ("forums", "Community Forums"),
    ("video", "Video Hub"),
    ("documents", "Document Library"),
    ("syllabus", "Class Syllabus"),
]

PORTAL_FEATURE_DEFAULTS: dict[str, bool] = {
    "messaging": True,
    "forums": False,
    "video": False,
    "documents": True,
    "syllabus": True,
}


def default_portal_features():
    return dict(PORTAL_FEATURE_DEFAULTS)


def default_social_links():
    return [
        {"platform": "Facebook", "url": "", "icon": "bi bi-facebook", "enabled": False},
        {
            "platform": "Instagram",
            "url": "",
            "icon": "bi bi-instagram",
            "enabled": False,
        },
        {"platform": "YouTube", "url": "", "icon": "bi bi-youtube", "enabled": False},
    ]


def default_admin_portal_stats_config():
    return {
        "sections": ["academics", "accounts", "finance"],
        "max_sections": 3,
        "max_items": 3,
        "items": {
            "academics": ["Students", "Classrooms", "Subjects"],
            "accounts": ["Users", "Teachers", "Guardians"],
            "finance": ["Invoices", "Overdue", "Draft"],
        },
    }


def default_portal_quick_actions():
    return [
        {
            "label": "Message Teacher",
            "url": "#",
            "icon": "bi-chat-dots",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "label": "View Report Card",
            "url": "#",
            "icon": "bi-file-earmark-text",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "label": "Request Meeting",
            "url": "#",
            "icon": "bi-calendar-event",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "label": "Download Documents",
            "url": "#",
            "icon": "bi-download",
            "roles": ["PARENT"],
            "enabled": True,
        },
    ]


def default_portal_announcements():
    return [
        {
            "title": "New Homework Policy",
            "meta": "2 days ago",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "title": "Sports Day Registration Open",
            "meta": "4 days ago",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "title": "Library Hours Extended",
            "meta": "1 week ago",
            "roles": ["PARENT"],
            "enabled": True,
        },
    ]


def default_portal_recent_grades():
    return [
        {
            "label": "Mathematics",
            "grade": "A (92%)",
            "tone": "success",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "label": "English",
            "grade": "A- (88%)",
            "tone": "success",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "label": "Science",
            "grade": "B+ (85%)",
            "tone": "primary",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "label": "History",
            "grade": "B (82%)",
            "tone": "warning",
            "roles": ["PARENT"],
            "enabled": True,
        },
    ]


def default_portal_upcoming_assessments():
    return [
        {
            "title": "Physics Test",
            "when": "Tomorrow",
            "detail": "Chapter 5-7",
            "tone": "info",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "title": "Math Quiz",
            "when": "Jan 28",
            "detail": "Algebra II",
            "tone": "secondary",
            "roles": ["PARENT"],
            "enabled": True,
        },
        {
            "title": "English Essay",
            "when": "Feb 2",
            "detail": "Due by 5 PM",
            "tone": "secondary",
            "roles": ["PARENT"],
            "enabled": True,
        },
    ]


def default_footer_badges():
    return [
        {"label": "Secure & Encrypted", "tone": "secure"},
        {"label": "2026 Standards Compliant", "tone": "compliant"},
    ]


def default_footer_links():
    return [
        {"label": "Privacy Policy", "url": "", "enabled": True, "roles": []},
        {"label": "Terms of Service", "url": "", "enabled": True, "roles": []},
        {"label": "About Us", "url": "", "enabled": True, "roles": []},
        {"label": "Documentation", "url": "", "enabled": True, "roles": []},
        {"label": "Support Center", "url": "", "enabled": True, "roles": []},
        {"label": "Compliance Reports", "url": "", "enabled": True, "roles": []},
    ]


def default_header_weather_config():
    return {
        "header_weather_location_id": None,
        "header_weather_country_code": "",
        "header_weather_city": "",
        "header_weather_label": "No location selected",
        "header_weather_latitude": 0.0,
        "header_weather_longitude": 0.0,
        "header_weather_timezone": getattr(settings, "TIME_ZONE", "UTC") or "UTC",
        "header_weather_temperature_unit": "celsius",
    }


def default_announcement_submit_for_approval_roles():
    return ["TEACHER", "COMMS_STAFF"]


def default_backend_feature_flags():
    weather = default_header_weather_config()
    return {
        "backend_warm_palette": True,
        "backend_reduce_card_flatness": True,
        "backend_high_depth_surfaces": True,
        "backend_balanced_motion": True,
        "backend_layout_equal_heights": True,
        "backend_layout_max_items_per_list": 5,
        "backend_viz_show_trend_ribbons": True,
        "backend_viz_show_progress_rings": True,
        "backend_viz_show_rank_sparklines": True,
        "backend_module_overview": True,
        "backend_module_admin_portal": True,
        "backend_module_welcome": True,
        "backend_module_enrollment_trends": True,
        "backend_module_at_risk_students": True,
        "backend_module_outstanding_fees": True,
        "backend_module_recent_admissions": True,
        "backend_module_recent_activity": True,
        "backend_module_top_performing": True,
        "backend_module_attendance_today": True,
        "backend_module_ops_watch": True,
        "backend_module_quick_links": True,
        "backend_module_planner": True,
        "enable_entity_console": True,
        "enable_entity_import": True,
        "enable_api_schema_ui": True,
        "enable_portal_pwa": True,
        "enable_offline_form_queue": True,
        "enable_offline_attendance_sync": True,
        "enable_offline_grade_sync": True,
        "enable_offline_payment_sync": True,
        "enable_offline_background_sync": True,
        "show_offline_status_bar": True,
        "show_header_context_strip": True,
        "show_header_context_datetime": True,
        "show_header_context_weather": False,
        "show_header_context_quote": True,
        "header_weather_country_code": weather["header_weather_country_code"],
        "header_weather_location_id": weather["header_weather_location_id"],
        "header_weather_city": weather["header_weather_city"],
        "header_weather_latitude": weather["header_weather_latitude"],
        "header_weather_longitude": weather["header_weather_longitude"],
        "header_weather_temperature_unit": weather["header_weather_temperature_unit"],
        "header_weather_timezone": weather["header_weather_timezone"],
        "header_weather_label": weather["header_weather_label"],
        "request_persistent_browser_storage": True,
        "reduce_activity_low_power": False,
        "reachability_url": "",
        "offline_entity_sync": True,
        "offline_requests_sync": True,
        "hub_base_url": "",
        "prefetch_at_hour": None,
        "max_bulk_import_rows": 500,
        "allow_bulk_commit": True,
        "allowed_roles_entity_console": ["ADMIN", "LEADERSHIP", "IT_ADMIN"],
        "allowed_roles_entity_import": ["ADMIN", "LEADERSHIP", "IT_ADMIN"],
        "allowed_roles_api_schema": ["ADMIN", "LEADERSHIP", "IT_ADMIN"],
        "require_guardian_finance_opt_in": True,
        "allow_finance_access_requests": True,
        "notify_parent_on_absence": True,
        "block_promotion_if_outstanding_returns": False,
        "block_report_download_if_outstanding_balance": True,
        "block_report_download_if_outstanding_returns": False,
        "carry_forward_arrears_on_rollover": True,
        "enable_cahier_de_texte": False,
        "cahier_syllabus_integration": "none",
        "enable_ocr_scan_teller": False,
        "enable_intervention_llm_roadmap": False,
        "enable_enrollment_forecast_api": False,
        "enable_seating_chart_beta": False,
        "enable_ministry_api_cartescolaire": False,
        "enable_ministry_api_dgi": False,
        "enable_ministry_live_sync": False,
        "enable_analytics_dashboard_cache": False,
        "enable_super_admin_ui": True,
        "marksheet_ocr_enabled": False,
        "marksheet_ocr_mobile_upload_enabled": True,
        "enable_api_center": False,
        "announcement_allow_submit_for_approval": False,
        "announcement_submit_for_approval_roles": default_announcement_submit_for_approval_roles(),
    }


def default_grade_approval_roles():
    return ["DEAN", "HOD"]


def default_grade_post_roles():
    return ["DEAN", "PRINCIPAL", "LEADERSHIP"]


def default_syllabus_approval_roles():
    return ["DEAN", "HOD"]


def default_delegation_role_mapping():
    return {
        "PRINCIPAL": ["VICE_PRINCIPAL", "HOD"],
        "VICE_PRINCIPAL": ["HOD", "DEAN"],
        "DEAN": ["HOD", "ACADEMICS_STAFF"],
        "HOD": ["DEPT_LEAD", "TEACHER"],
        "TEACHER": ["TEACHER"],
        "BURSAR": ["FINANCE_STAFF"],
    }


def virtual_site_setting_default(name: str) -> object:
    """
    Safe defaults for legacy tenant-settings payload keys that live in RuntimeDefaults.payload when the key
    is absent. Keeps templates and owned_payload(getattr) from raising or returning unusable nulls.
    """
    from decimal import Decimal

    from .models import (
        PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        PLATFORM_DEFAULT_SCHOOL_CODE,
        PLATFORM_DEFAULT_SITE_NAME,
        PLATFORM_DEFAULT_TAGLINE,
    )

    _factories: dict[str, object] = {
        "backend_feature_flags": default_backend_feature_flags,
        "portal_features": default_portal_features,
        "social_links": default_social_links,
        "admin_portal_stats_config": default_admin_portal_stats_config,
        "portal_quick_actions": default_portal_quick_actions,
        "portal_announcements": default_portal_announcements,
        "portal_recent_grades": default_portal_recent_grades,
        "portal_upcoming_assessments": default_portal_upcoming_assessments,
        "grade_approval_roles": default_grade_approval_roles,
        "grade_post_roles": default_grade_post_roles,
        "syllabus_approval_roles": default_syllabus_approval_roles,
        "delegation_role_mapping": default_delegation_role_mapping,
    }
    factory = _factories.get(name)
    if callable(factory):
        return factory()

    _lists = {"notification_channels", "require_mfa_roles"}
    if name in _lists:
        return []

    if name == "default_widgets_per_role":
        return {}

    _strings: dict[str, str] = {
        "site_name": PLATFORM_DEFAULT_SITE_NAME,
        "school_code": PLATFORM_DEFAULT_SCHOOL_CODE,
        "tagline": PLATFORM_DEFAULT_TAGLINE,
        "meta_description": "",
        "company_name": "",
        "company_address": "",
        "company_phone": "",
        "company_email": "",
        "company_slug": "",
        "branded_domain": "",
        "custom_css": "",
        "backend_console_theme": "auto",
        "primary_color": "#0d6efd",
        "accent_color": "#198754",
        "success_color": "#22c55e",
        "warning_color": "#f59e0b",
        "danger_color": "#ef4444",
        "header_bg_color": "#0f172a",
        "footer_bg_color": "#0f172a",
        "theme_brightness": "system",
        "theme_harmony": "polychromatic",
        "secondary_font": "",
        "default_dashboard_view": "",
        "default_report_preview_type": "TERM",
        "offline_sync_conflict_resolution": "show_both",
        "report_preview_contact_email": PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        "report_preview_contact_phone": "",
        "sms_provider": "",
        "sms_api_key": "",
        "ai_provider_api_key": "",
        "whatsapp_api_token": "",
        "sms_sender_id": "",
        "email_from_address": "",
        "smtp_password": "",
        "webhook_signing_secret": "",
        "marketplace_partner_client_secret": "",
        "whatsapp_support_number": "",
        "whatsapp_admissions_number": "",
        "marksheet_ocr_command": "",
        "marksheet_ocr_api_key": "",
        "admission_number_mode": "",
        "admission_number_pattern": "",
        "admission_number_strategy": "",
        "admission_number_template": "",
        "country": "",
        "region": "",
        "ministry": "",
        "default_region": "",
        "default_grading_scale": "",
        "ministry_registration_code": "",
    }
    if name in _strings:
        return _strings[name]

    if name == "compliance_profile_id":
        return None

    _ints = {
        "cache_rankings_interval_minutes": 60,
        "requests_reminder_interval_hours": 24,
        "teacher_reminder_time_of_day": 8,
        "top_students_default_limit": 5,
        "default_refresh_rate": 60,
        "base_font_size": 16,
    }
    if name in _ints:
        return _ints[name]

    if name == "referral_bonus_amount":
        return Decimal("0")

    _bool_true = {
        "enable_parent_portal",
        "enable_teacher_portal",
        "enable_concurrent_mark_uploads",
        "enable_reports_pdf",
        "notify_parent_welcome_email",
    }
    if name in _bool_true:
        return True

    _bool_false = {
        "preview_mode_enabled",
        "use_dark_mode",
        "default_sidebar_collapsed",
        "use_secondary_font_for_headings",
        "admin_use_site_primary",
        "skip_theme_publish_guard",
        "default_portal_role_dual_role",
        "grade_approval_enabled",
        "enable_practical_assessment",
        "require_mfa_all_staff",
        "use_promotion_rule_for_pass",
        "enable_offline_mode",
        "auto_tag_photos_from_exif",
        "reports_require_approved_grades_before_publish",
        "reports_use_approved_grades_only",
        "enable_whatsapp_parent_portal",
        "enable_whatsapp_staff_portal",
    }
    if name in _bool_false:
        return False

    if name.startswith("enable_") or name.endswith("_enabled"):
        return False
    if name.startswith("use_") or name.startswith("require_"):
        return False
    if name.startswith("show_") or name.startswith("allow_") or name.startswith("block_"):
        return False

    return ""


def get_theme_pack_owner_model():
    try:
        model = django_apps.get_model("brand_experience", "ThemePack")
        if model is not None:
            return model
    except LookupError:
        pass
    from .models import ThemePack

    return ThemePack


def get_report_card_style_owner_model():
    try:
        model = django_apps.get_model("runtime_blueprints", "ReportCardStyle")
        if model is not None:
            return model
    except LookupError:
        pass
    from .models import ReportCardStyle

    return ReportCardStyle


def _site_settings_json_safe(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_site_settings_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _site_settings_json_safe(item) for key, item in value.items()}
    if hasattr(value, "pk"):
        return value.pk
    if isinstance(value, FieldFile):
        try:
            return value.url or str(value)
        except (AttributeError, TypeError, ValueError):
            name = getattr(value, "name", None)
            return str(name) if name else None
    return str(value)


def _platform_placeholder_defaults() -> dict[str, object]:
    from .models import (
        PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        PLATFORM_DEFAULT_SCHOOL_CODE,
        PLATFORM_DEFAULT_SITE_NAME,
        PLATFORM_DEFAULT_TAGLINE,
        PLATFORM_SCRUB_REPORT_PREVIEW_EMAIL_DOMAINS,
        PLATFORM_SCRUB_REPORT_PREVIEW_PHONES,
        PLATFORM_SCRUB_SCHOOL_CODES,
        PLATFORM_SCRUB_SITE_NAMES,
        PLATFORM_SCRUB_TAGLINES,
    )

    return {
        "site_name": PLATFORM_DEFAULT_SITE_NAME,
        "school_code": PLATFORM_DEFAULT_SCHOOL_CODE,
        "tagline": PLATFORM_DEFAULT_TAGLINE,
        "report_preview_email": PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        "scrub_site_names": PLATFORM_SCRUB_SITE_NAMES,
        "scrub_school_codes": PLATFORM_SCRUB_SCHOOL_CODES,
        "scrub_taglines": PLATFORM_SCRUB_TAGLINES,
        "scrub_report_email_domains": PLATFORM_SCRUB_REPORT_PREVIEW_EMAIL_DOMAINS,
        "scrub_report_phones": PLATFORM_SCRUB_REPORT_PREVIEW_PHONES,
    }


def _normalized_site_name(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip()
    return defaults["site_name"] if text in defaults["scrub_site_names"] else text


def _normalized_school_code(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip().upper()
    return defaults["school_code"] if text in defaults["scrub_school_codes"] else text


def _normalized_tagline(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip()
    return defaults["tagline"] if text in defaults["scrub_taglines"] else text


def _normalized_report_preview_email(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip().lower()
    local_part, _, domain = text.partition("@")
    is_scrub_match = not text or (
        local_part == "reports" and domain in defaults["scrub_report_email_domains"]
    )
    return defaults["report_preview_email"] if is_scrub_match else text


def _normalized_report_preview_phone(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip()
    return "" if text in defaults["scrub_report_phones"] else text


def _payload_or_attr(
    payload: dict[str, object],
    instance: object,
    field_name: str,
    default: object = None,
) -> object:
    return payload.get(field_name, getattr(instance, field_name, default))


def _payload_string(
    payload: dict[str, object],
    instance: object,
    field_name: str,
    default: str = "",
) -> str:
    return str(_payload_or_attr(payload, instance, field_name, default) or default)


def _payload_bool(
    payload: dict[str, object],
    instance: object,
    field_name: str,
    default: bool = False,
) -> bool:
    return bool(_payload_or_attr(payload, instance, field_name, default))


def _payload_int(
    payload: dict[str, object],
    instance: object,
    field_name: str,
    default: int = 0,
) -> int:
    value = _payload_or_attr(payload, instance, field_name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _payload_float(
    payload: dict[str, object],
    instance: object,
    field_name: str,
    default: float = 0.0,
) -> float:
    value = _payload_or_attr(payload, instance, field_name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _payload_decimal(
    payload: dict[str, object],
    instance: object,
    field_name: str,
    default: str | Decimal = "0.00",
) -> Decimal:
    value = _payload_or_attr(payload, instance, field_name, default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))


def _payload_json_object(
    payload: dict[str, object],
    instance: object,
    field_name: str,
) -> dict[str, object]:
    value = _payload_or_attr(payload, instance, field_name, {})
    return dict(value) if isinstance(value, dict) else {}


def _payload_string_list(
    payload: dict[str, object],
    instance: object,
    field_name: str,
) -> list[str]:
    value = _payload_or_attr(payload, instance, field_name, [])
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _payload_int_list(
    payload: dict[str, object],
    instance: object,
    field_name: str,
) -> list[int]:
    value = _payload_or_attr(payload, instance, field_name, [])
    if not isinstance(value, (list, tuple)):
        return []
    normalized: list[int] = []
    for item in value:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue
    return normalized


def filter_portal_items(items, role: str | None) -> list[dict]:
    if not isinstance(items, list):
        return []
    role_value = (role or "").upper()
    filtered = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue
        roles = item.get("roles") or []
        if roles and role_value not in [str(r).upper() for r in roles]:
            continue
        filtered.append(item)
    return filtered


class DashboardView:
    OVERVIEW = "OVERVIEW"
    WORKFLOW = "WORKFLOW"
    FINANCE = "FINANCE"
    ACADEMICS = "ACADEMICS"
    ATTENDANCE = "ATTENDANCE"
    CERTIFICATION = "CERTIFICATION"
    CUSTOM = "CUSTOM"
    choices = [
        (OVERVIEW, "Overview"),
        (WORKFLOW, "Workflow Center"),
        (FINANCE, "Finances"),
        (ACADEMICS, "Academics"),
        (ATTENDANCE, "Attendance"),
        (CERTIFICATION, "Certification & Exams"),
        (CUSTOM, "Custom"),
    ]


class ThemeLayout:
    STANDARD = "STANDARD"
    WIDE = "WIDE"
    CARD = "CARD"
    MINIMAL = "MINIMAL"
    choices = [
        (STANDARD, "Standard"),
        (WIDE, "Wide"),
        (CARD, "Card focus"),
        (MINIMAL, "Minimal"),
    ]


DASHBOARD_WIDGET_OPTIONS = [
    ("attendance", "Attendance snapshot"),
    ("performance", "Performance overview"),
    ("finance", "Financial summary"),
    ("events", "Events & alerts"),
    ("tasks", "Task tracker"),
    ("communications", "Communication center"),
    ("referral", "Referral health"),
    ("access", "Portal access"),
    ("system_status", "System status"),
    ("completion", "Completion drill"),
    ("analytics", "Analytics insights"),
    ("upcoming", "Upcoming classes"),
    ("links", "Quick actions"),
    ("certification", "Certification & Exams"),
]

ROLE_WIDGET_DEFAULTS = {
    User.Role.PARENT: [
        "attendance",
        "performance",
        "finance",
        "events",
        "tasks",
        "communications",
        "referral",
        "access",
        "system_status",
        "analytics",
    ],
    User.Role.TEACHER: [
        "completion",
        "tasks",
        "finance",
        "attendance",
        "communications",
        "upcoming",
        "links",
        "analytics",
    ],
    User.Role.ADMIN: [
        "system_status",
        "finance",
        "attendance",
        "events",
        "analytics",
        "access",
        "certification",
    ],
}


def default_dashboard_widgets(role: str | None) -> list[str]:
    role_key = (role or "").upper()
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        site = get_effective_site_settings()
        if site is None:
            raise LookupError("effective site settings unavailable")
        per_role = getattr(site, "default_widgets_per_role", None) or {}
        if isinstance(per_role, dict) and role_key in per_role:
            role_list = per_role.get(role_key)
            if isinstance(role_list, list) and role_list:
                valid_ids = {key for key, _ in DASHBOARD_WIDGET_OPTIONS}
                filtered = [w for w in role_list if str(w).strip() in valid_ids]
                if filtered:
                    return filtered
    except (AttributeError, ImportError, LookupError, TypeError, ValueError):
        pass
    return list(
        ROLE_WIDGET_DEFAULTS.get(role_key, [key for key, _ in DASHBOARD_WIDGET_OPTIONS])
    )


def get_dashboard_widget_choices(role: str | None) -> list[tuple[str, str]]:
    allowed = set(default_dashboard_widgets(role))
    return [(key, label) for key, label in DASHBOARD_WIDGET_OPTIONS if key in allowed]


def resolve_dashboard_widgets(
    role: str | None, preference: "UserPreference | None" = None
) -> list[str]:
    allowed = default_dashboard_widgets(role)
    if preference:
        if preference.dashboard_view == DashboardView.CUSTOM:
            selected = []
            dashboard_pref = None
            try:
                from apps.siteconfig.models_dashboard import DashboardUserPreference

                dashboard_pref = preference.user.dashboard_preferences
            except (DashboardUserPreference.DoesNotExist, AttributeError):
                dashboard_pref = None
            if dashboard_pref:
                selected = [
                    key
                    for key in dashboard_pref.get_dashboard_widgets()
                    if key in allowed
                ]
            if not selected:
                selected = [
                    key for key in preference.dashboard_widgets if key in allowed
                ]
            return selected or allowed
        view_map = {
            DashboardView.FINANCE: ["finance", "events", "communications", "links"],
            DashboardView.ATTENDANCE: ["attendance", "events", "tasks", "links"],
            DashboardView.ACADEMICS: [
                "performance",
                "completion",
                "upcoming",
                "analytics",
                "tasks",
                "links",
            ],
            DashboardView.CERTIFICATION: [
                "certification",
                "performance",
                "tasks",
                "links",
                "events",
            ],
        }
        mapped = view_map.get(preference.dashboard_view)
        if mapped:
            filtered = [key for key in mapped if key in allowed]
            return filtered or allowed
    return allowed


def build_platform_default_site_settings():
    import apps.siteconfig.models as _siteconfig_models

    from .models import (
        PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        PLATFORM_DEFAULT_SCHOOL_CODE,
        PLATFORM_DEFAULT_SITE_NAME,
        PLATFORM_DEFAULT_TAGLINE,
    )

    _TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")
    site = _TenantSettingsModel()
    site.pk = 1
    object.__setattr__(site, "site_name", PLATFORM_DEFAULT_SITE_NAME)
    object.__setattr__(site, "school_code", PLATFORM_DEFAULT_SCHOOL_CODE)
    object.__setattr__(site, "tagline", PLATFORM_DEFAULT_TAGLINE)
    object.__setattr__(
        site, "report_preview_contact_email", PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL
    )
    object.__setattr__(site, "report_preview_contact_phone", "")
    return site
