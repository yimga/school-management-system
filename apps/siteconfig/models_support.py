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
        {"platform": "Instagram", "url": "", "icon": "bi bi-instagram", "enabled": False},
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
        {"title": "New Homework Policy", "meta": "2 days ago", "roles": ["PARENT"], "enabled": True},
        {"title": "Sports Day Registration Open", "meta": "4 days ago", "roles": ["PARENT"], "enabled": True},
        {"title": "Library Hours Extended", "meta": "1 week ago", "roles": ["PARENT"], "enabled": True},
    ]


def default_portal_recent_grades():
    return [
        {"label": "Mathematics", "grade": "A (92%)", "tone": "success", "roles": ["PARENT"], "enabled": True},
        {"label": "English", "grade": "A- (88%)", "tone": "success", "roles": ["PARENT"], "enabled": True},
        {"label": "Science", "grade": "B+ (85%)", "tone": "primary", "roles": ["PARENT"], "enabled": True},
        {"label": "History", "grade": "B (82%)", "tone": "warning", "roles": ["PARENT"], "enabled": True},
    ]


def default_portal_upcoming_assessments():
    return [
        {"title": "Physics Test", "when": "Tomorrow", "detail": "Chapter 5-7", "tone": "info", "roles": ["PARENT"], "enabled": True},
        {"title": "Math Quiz", "when": "Jan 28", "detail": "Algebra II", "tone": "secondary", "roles": ["PARENT"], "enabled": True},
        {"title": "English Essay", "when": "Feb 2", "detail": "Due by 5 PM", "tone": "secondary", "roles": ["PARENT"], "enabled": True},
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
        LEGACY_PLACEHOLDER_REPORT_DOMAINS,
        LEGACY_PLACEHOLDER_REPORT_PHONES,
        LEGACY_PLACEHOLDER_SCHOOL_CODES,
        LEGACY_PLACEHOLDER_SITE_NAMES,
        LEGACY_PLACEHOLDER_TAGLINES,
        PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        PLATFORM_DEFAULT_SCHOOL_CODE,
        PLATFORM_DEFAULT_SITE_NAME,
        PLATFORM_DEFAULT_TAGLINE,
    )

    return {
        "site_name": PLATFORM_DEFAULT_SITE_NAME,
        "school_code": PLATFORM_DEFAULT_SCHOOL_CODE,
        "tagline": PLATFORM_DEFAULT_TAGLINE,
        "report_preview_email": PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        "legacy_site_names": LEGACY_PLACEHOLDER_SITE_NAMES,
        "legacy_school_codes": LEGACY_PLACEHOLDER_SCHOOL_CODES,
        "legacy_taglines": LEGACY_PLACEHOLDER_TAGLINES,
        "legacy_report_domains": LEGACY_PLACEHOLDER_REPORT_DOMAINS,
        "legacy_report_phones": LEGACY_PLACEHOLDER_REPORT_PHONES,
    }


def _normalized_site_name(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip()
    return defaults["site_name"] if text in defaults["legacy_site_names"] else text


def _normalized_school_code(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip().upper()
    return defaults["school_code"] if text in defaults["legacy_school_codes"] else text


def _normalized_tagline(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip()
    return defaults["tagline"] if text in defaults["legacy_taglines"] else text


def _normalized_report_preview_email(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip().lower()
    local_part, _, domain = text.partition("@")
    is_legacy_placeholder = not text or (
        local_part == "reports" and domain in defaults["legacy_report_domains"]
    )
    return defaults["report_preview_email"] if is_legacy_placeholder else text


def _normalized_report_preview_phone(value: object) -> str:
    defaults = _platform_placeholder_defaults()
    text = str(value or "").strip()
    return "" if text in defaults["legacy_report_phones"] else text


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
        from apps.platform_runtime.helpers import get_effective_site_settings

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
    return list(ROLE_WIDGET_DEFAULTS.get(role_key, [key for key, _ in DASHBOARD_WIDGET_OPTIONS]))


def get_dashboard_widget_choices(role: str | None) -> list[tuple[str, str]]:
    allowed = set(default_dashboard_widgets(role))
    return [(key, label) for key, label in DASHBOARD_WIDGET_OPTIONS if key in allowed]


def resolve_dashboard_widgets(role: str | None, preference: "UserPreference | None" = None) -> list[str]:
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
                selected = [key for key in dashboard_pref.get_dashboard_widgets() if key in allowed]
            if not selected:
                selected = [key for key in preference.dashboard_widgets if key in allowed]
            return selected or allowed
        view_map = {
            DashboardView.FINANCE: ["finance", "events", "communications", "links"],
            DashboardView.ATTENDANCE: ["attendance", "events", "tasks", "links"],
            DashboardView.ACADEMICS: ["performance", "completion", "upcoming", "analytics", "tasks", "links"],
            DashboardView.CERTIFICATION: ["certification", "performance", "tasks", "links", "events"],
        }
        mapped = view_map.get(preference.dashboard_view)
        if mapped:
            filtered = [key for key in mapped if key in allowed]
            return filtered or allowed
    return allowed


def build_platform_default_site_settings():
    from .models import (
        PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL,
        PLATFORM_DEFAULT_SCHOOL_CODE,
        PLATFORM_DEFAULT_SITE_NAME,
        PLATFORM_DEFAULT_TAGLINE,
        SiteSettings,
    )

    site = SiteSettings()
    site.pk = 1
    site.site_name = PLATFORM_DEFAULT_SITE_NAME
    site.school_code = PLATFORM_DEFAULT_SCHOOL_CODE
    site.tagline = PLATFORM_DEFAULT_TAGLINE
    site.report_preview_contact_email = PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL
    site.report_preview_contact_phone = ""
    return site
