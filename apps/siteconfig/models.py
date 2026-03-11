from __future__ import annotations

from decimal import Decimal
import logging
import uuid

from django.conf import settings
from django.db import models, connection, OperationalError, DatabaseError
from django.db.models import Q
from django.db.models.fields.files import FieldFile
from django.db.models.signals import post_delete, post_save
from django.core.validators import MinValueValidator, MaxValueValidator
from .image_utils import optimize_image
from django.apps import apps as django_apps

from apps.accounts.models import User
from apps.academics.models import Classroom, Subject
from apps.people.models import StudentProfile, TeacherProfile, StudentGuardian
from apps.siteconfig.global_catalog import GlobalGeoCatalog

logger = logging.getLogger(__name__)

# Phase 2/7: Tenant behavior must not be sourced from SiteSettings; use runtime resolvers and
# bounded-context services. Migration plan: docs/SITECONFIG_OWNERSHIP_MIGRATION.md

REPORT_CARD_TYPE_TERM = "TERM"
REPORT_CARD_TYPE_ANNUAL = "ANNUAL"


def _tenant_upload_to(subpath):
    """
    Phase F: Return an upload_to callable that prefixes path with tenants/{school_id}/.
    Use for any FileField/ImageField on a model with a school FK to avoid cross-tenant access.
    """
    def upload_to(instance, filename):
        school_id = getattr(instance, "school_id", None)
        if school_id is None and getattr(instance, "school", None):
            school_id = getattr(instance.school, "pk", None)
        if school_id is None:
            return f"tenant_uploads/{subpath}/{filename}"
        return f"tenants/{school_id}/{subpath}/{filename}"
    return upload_to


def tenant_upload_to_waiver_requests(instance, filename):
    """Serializable upload_to for WaiverRequest.proof_file (migrations)."""
    return _tenant_upload_to("waiver_requests")(instance, filename)


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


def default_backend_feature_flags():
    weather = default_header_weather_config()
    return {
        # Backend dashboard experience + visualization controls
        "backend_warm_palette": True,
        "backend_reduce_card_flatness": True,
        "backend_high_depth_surfaces": True,
        "backend_balanced_motion": True,
        "backend_layout_equal_heights": True,
        "backend_layout_max_items_per_list": 5,
        "backend_viz_show_trend_ribbons": True,
        "backend_viz_show_progress_rings": True,
        "backend_viz_show_rank_sparklines": True,
        # Backend module visibility toggles
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


def default_announcement_submit_for_approval_roles():
    return ["TEACHER", "COMMS_STAFF"]


def default_grade_approval_roles():
    return ["DEAN", "HOD"]


def default_grade_post_roles():
    return ["DEAN", "PRINCIPAL", "LEADERSHIP"]


def default_syllabus_approval_roles():
    return ["DEAN", "HOD"]


def default_delegation_role_mapping():
    """Who can delegate to whom: {delegator_role: [allowed_delegate_roles]}."""
    return {
        "PRINCIPAL": ["VICE_PRINCIPAL", "HOD"],
        "VICE_PRINCIPAL": ["HOD", "DEAN"],
        "DEAN": ["HOD", "ACADEMICS_STAFF"],
        "HOD": ["DEPT_LEAD", "TEACHER"],
        "TEACHER": ["TEACHER"],
        "BURSAR": ["FINANCE_STAFF"],
    }


_SITE_SETTINGS_CACHE: "SiteSettings | None" = None

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


class DashboardView(models.TextChoices):
    OVERVIEW = "OVERVIEW", "Overview"
    WORKFLOW = "WORKFLOW", "Workflow Center"
    FINANCE = "FINANCE", "Finances"
    ACADEMICS = "ACADEMICS", "Academics"
    ATTENDANCE = "ATTENDANCE", "Attendance"
    CERTIFICATION = "CERTIFICATION", "Certification & Exams"
    CUSTOM = "CUSTOM", "Custom"


class ThemeLayout(models.TextChoices):
    STANDARD = "STANDARD", "Standard"
    WIDE = "WIDE", "Wide"
    CARD = "CARD", "Card focus"
    MINIMAL = "MINIMAL", "Minimal"


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


# DEPRECATED: Prefer apps.platform_runtime.helpers.get_effective_site_settings and bounded-context
# services for tenant behavior. Use SiteSettings only for platform defaults. Removal target: post Phase 10.
class SiteSettings(models.Model):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_backend_feature_flags = (self.backend_feature_flags or {}).copy()

    video_background = models.FileField(
        upload_to="branding/video/",
        blank=True,
        null=True,
        help_text="Optional: Short looping video (mp4/webm) for animated background."
    )
    svg_background = models.FileField(
        upload_to="branding/svg/",
        blank=True,
        null=True,
        help_text="Optional: SVG file for animated or vector background."
    )
    # Branding
    site_name = models.CharField(max_length=120, default="School System")
    tagline = models.CharField(max_length=200, blank=True, default="Knowledge ƒ?› Technology ƒ?› Excellence")
    meta_description = models.CharField(
        max_length=320,
        blank=True,
        default="",
        help_text="Optional SEO meta description for pages (used in base/portal_base templates).",
    )
    logo = models.ImageField(upload_to="branding/", blank=True, null=True)
    logo_opacity = models.FloatField(
        default=0.3,
        blank=True,
        null=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Opacity for logo background (0.0 = fully transparent, 1.0 = fully opaque)"
    )
    LOGO_BG_MODE_CHOICES = [
        ("none", "None (disabled)"),
        ("contain", "Contain (default)"),
        ("cover", "Cover"),
        ("tile", "Tile/Repeat"),
        ("center", "Center (no scale)"),
    ]
    logo_background_mode = models.CharField(
        max_length=16,
        choices=LOGO_BG_MODE_CHOICES,
        default="contain",
        help_text="How the logo background image is displayed: contain, cover, tile, or center."
    )
    BRIGHTNESS_CHOICES = [
        ("system", "System"),
        ("light", "Light"),
        ("dark", "Dark"),
        ("classic", "Classic"),
        ("high_contrast", "High Contrast"),
    ]
    theme_brightness = models.CharField(
        max_length=16,
        choices=BRIGHTNESS_CHOICES,
        default="system",
        help_text="Choose default theme brightness (System/Light/Dark/Classic/High Contrast)."
    )
    background_image = models.ImageField(upload_to="branding/bg/", blank=True, null=True)

    def save(self, *args, **kwargs):
        before = getattr(self, "_orig_backend_feature_flags", {}) or {}
        after = self.backend_feature_flags or {}
        changed_opt_in = before.get("require_guardian_finance_opt_in") != after.get("require_guardian_finance_opt_in")

        # Optimize logo
        if self.logo and hasattr(self.logo, 'file') and not getattr(self.logo.file, '_optimized', False):
            optimized = optimize_image(self.logo)
            if optimized:
                optimized._optimized = True
                self.logo.save(self.logo.name, optimized, save=False)
        # Optimize background image
        if self.background_image and hasattr(self.background_image, 'file') and not getattr(self.background_image.file, '_optimized', False):
            optimized = optimize_image(self.background_image)
            if optimized:
                optimized._optimized = True
                self.background_image.save(self.background_image.name, optimized, save=False)
        # Optimize favicon and sidebar icon
        for field_name in ("favicon", "sidebar_icon"):
            field = getattr(self, field_name, None)
            if field and hasattr(field, "file") and not getattr(field.file, "_optimized", False):
                optimized = optimize_image(field)
                if optimized:
                    optimized._optimized = True
                    field.save(field.name, optimized, save=False)
        try:
            super().save(*args, **kwargs)
        except DatabaseError as exc:
            if kwargs.get("update_fields") and "update_fields did not affect any rows" in str(exc):
                retry_kwargs = dict(kwargs)
                retry_kwargs.pop("update_fields", None)
                super().save(*args, **retry_kwargs)
            else:
                raise

        if changed_opt_in:
            logger.info(
                "require_guardian_finance_opt_in changed",
                extra={"from": before.get("require_guardian_finance_opt_in"), "to": after.get("require_guardian_finance_opt_in")},
            )
        self._orig_backend_feature_flags = after.copy()

    brand_font = models.CharField(max_length=120, default="Inter, system-ui, sans-serif")
    school_code = models.CharField(
        max_length=20,
        default="SCH",
        help_text="Short code used in admission numbers (e.g., SCH).",
    )
    class AdmissionNumberMode(models.TextChoices):
        AUTO = "AUTO", "Auto-generate (recommended)"
        MANUAL = "MANUAL", "Manual entry only"
        AUTO_OR_MANUAL = "AUTO_OR_MANUAL", "Allow auto or manual"

    admission_number_mode = models.CharField(
        max_length=20,
        choices=AdmissionNumberMode.choices,
        default=AdmissionNumberMode.AUTO_OR_MANUAL,
        help_text=(
            "Controls whether student admission numbers are auto-generated, "
            "entered manually, or can be either. In AUTO/AUTO_OR_MANUAL modes, "
            "leaving the field blank will generate a number using the school code."
        ),
    )
    admission_number_pattern = models.CharField(
        max_length=255,
        blank=True,
        default=(
            r"(\\d{2}[A-Z0-9]{2,10}\\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4})|"
            r"(\\d{2}-[A-Z0-9]{2,10}-\\d{4}-[A-Z0-9]{2,6}-[A-Z0-9]{1,4})"
        ),
        help_text=(
            "Regex used to validate admission numbers. "
            "Defaults to YY + SCHOOL + #### + SPEC + CLASS (no dashes) "
            "or the legacy dashed format."
        ),
    )
    class AdmissionNumberStrategy(models.TextChoices):
        FULL = "FULL", "Full (YY+School+Seq+Spec+Class)"
        YEAR_SEQ = "YEAR_SEQ", "Year + sequence only"
        SEQ_ONLY = "SEQ_ONLY", "Sequence only"

    admission_number_strategy = models.CharField(
        max_length=20,
        choices=AdmissionNumberStrategy.choices,
        default=AdmissionNumberStrategy.FULL,
        blank=True,
        help_text="Built-in generation strategy when no template is set.",
    )
    admission_number_template = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Optional template with placeholders: {year_2digit}, {school_code}, "
            "{seq_4digit}, {spec_code}, {class_segment}. Overrides strategy when set."
        ),
    )
    company_name = models.CharField(max_length=160, blank=True, default="")
    company_address = models.TextField(blank=True, default="")
    company_phone = models.CharField(max_length=50, blank=True, default="")
    company_email = models.EmailField(blank=True, default="")
    ministry_registration_code = models.CharField(max_length=80, blank=True, default="")
    company_slug = models.SlugField(max_length=120, blank=True, default="")
    country = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Country where the school is located.",
    )
    region = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Region, division, or state where the school operates.",
    )
    ministry = models.CharField(
        max_length=160,
        blank=True,
        default="",
        help_text="Oversight ministry, delegation, or authority.",
    )

    # Theme configuration
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    header_bg_color = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Optional: Header background color (hex). Leave blank to use primary→accent gradient.",
    )
    footer_bg_color = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Optional: Footer background color (hex). Leave blank for default.",
    )
    success_color = models.CharField(max_length=20, default="#22c55e")
    warning_color = models.CharField(max_length=20, default="#fbbf24")
    danger_color = models.CharField(max_length=20, default="#ef4444")
    use_dark_mode = models.BooleanField(default=False)
    BACKEND_CONSOLE_THEME_CHOICES = [
        ("dark", "Dark (slate grey)"),
        ("light", "Light (lavender tint)"),
        ("system", "System (follows OS)"),
        ("black", "Black (true black #000)"),
        ("ink", "Ink (deep black #030712)"),
        ("onyx", "Onyx (rich black #0c0c0c)"),
        ("charcoal", "Charcoal (soft black)"),
        ("graphite", "Graphite (zinc grey)"),
        ("midnight", "Midnight (deep blue-black)"),
        ("ocean", "Ocean (dark blue)"),
        ("steel", "Steel (blue-grey)"),
        ("slate", "Slate (medium grey)"),
        ("forest", "Forest (dark green)"),
        ("indigo", "Indigo (dark purple)"),
        ("amber", "Amber (warm dark)"),
        ("sand", "Sand (warm light)"),
        ("snow", "Snow (cool light)"),
        ("cream", "Cream (ivory light)"),
        ("lavender", "Lavender (soft purple light)"),
    ]
    backend_console_theme = models.CharField(
        max_length=20,
        choices=BACKEND_CONSOLE_THEME_CHOICES,
        default="dark",
        help_text="Theme for the Backend Console (Workflow Center, Entity Console).",
    )
    custom_css = models.TextField(blank=True)
    theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_settings",
        help_text="Theme for portal (parent, teacher, student dashboards). Does not affect /admin or /backend.",
    )
    admin_theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_site_settings",
        help_text="Theme for staff dashboards: /admin and /backend. Shared between both.",
    )
    teacher_theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_settings_teacher",
        help_text="Optional: Theme pack for teachers on the portal. If unset, portal theme pack is used.",
    )
    parent_theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_settings_parent",
        help_text="Optional: Theme pack for parents on the portal. If unset, portal theme pack is used.",
    )
    skip_theme_publish_guard = models.BooleanField(
        default=False,
        help_text="When enabled, theme pack and high-impact theme changes save without requiring live preview confirmation. Use only in low-risk environments.",
    )
    preview_mode_enabled = models.BooleanField(default=False)
    preview_note = models.CharField(max_length=255, blank=True, default="")

    # Theme Phase A–D: login, header, layout, sidebar, email, nav, typography
    login_hero_heading = models.CharField(
        max_length=160,
        blank=True,
        default="",
        help_text="Optional heading for the login hero (e.g. 'Welcome to Our School'). Leave blank to use site name.",
    )
    login_hero_subtext = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional subtext for the login hero. Leave blank to use tagline.",
    )
    show_header_search = models.BooleanField(
        default=True,
        help_text="Show search in the portal/backend header.",
    )
    show_header_notifications = models.BooleanField(
        default=True,
        help_text="Show notifications bell in the header.",
    )
    show_header_profile_menu = models.BooleanField(
        default=True,
        help_text="Show user profile / quick links in the header.",
    )
    show_header_theme_toggle = models.BooleanField(
        default=True,
        help_text="Show theme (light/dark) toggle in the header when applicable.",
    )
    favicon = models.ImageField(
        upload_to="branding/",
        blank=True,
        null=True,
        help_text="Favicon for browser tabs. Shown across portal, backend, and admin.",
    )
    LAYOUT_STYLE_CHOICES = [
        ("fluid", "Fluid (full width)"),
        ("boxed", "Boxed (max-width container)"),
    ]
    layout_style = models.CharField(
        max_length=10,
        choices=LAYOUT_STYLE_CHOICES,
        default="fluid",
        help_text="Page layout: fluid (full width) or boxed (centered max-width).",
    )
    default_sidebar_collapsed = models.BooleanField(
        default=False,
        help_text="When True, new users see the nav sidebar collapsed by default.",
    )
    branded_domain = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Display-only domain for login and emails (e.g. portal.school.edu). No DNS logic.",
    )
    portal_sidebar_order = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional list of portal sidebar item IDs in display order. Empty = use template default.",
    )
    sidebar_icon = models.ImageField(
        upload_to="branding/",
        blank=True,
        null=True,
        help_text="Optional small icon shown when the nav sidebar is collapsed.",
    )
    secondary_font = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Optional secondary font (e.g. for headings). Leave blank to use primary font.",
    )
    use_secondary_font_for_headings = models.BooleanField(
        default=False,
        help_text="When True, use secondary_font for headings (h1–h6).",
    )
    base_font_size = models.PositiveSmallIntegerField(
        default=16,
        blank=True,
        null=True,
        help_text="Base font size in pixels for rem-based typography. Null = use CSS default.",
    )
    default_widgets_per_role = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional: role code -> list of widget IDs for default dashboard (e.g. {\"TEACHER\": [\"widget-a\", \"widget-b\"]}).",
    )
    admin_use_site_primary = models.BooleanField(
        default=False,
        help_text="When True, admin sidebar active/accent uses SiteSettings.primary_color.",
    )

    # Behavior & personalization defaults
    maintenance_mode = models.BooleanField(default=False)
    default_dashboard_view = models.CharField(
        max_length=20,
        choices=DashboardView.choices,
        default=DashboardView.OVERVIEW,
    )
    default_refresh_rate = models.PositiveSmallIntegerField(
        default=60,
        help_text="Interval in seconds before dashboards refresh automatically.",
    )
    notification_channels = models.JSONField(default=list, blank=True)
    admin_portal_stats_config = models.JSONField(
        default=default_admin_portal_stats_config,
        blank=True,
        help_text=(
            "Admin portal stats JSON. Keys: sections, max_sections, max_items, items. "
            "Example: {\"sections\":[\"academics\"],\"max_items\":2,\"items\":{\"academics\":[\"Students\"]}}"
        ),
    )
    portal_quick_actions = models.JSONField(
        default=default_portal_quick_actions,
        blank=True,
        help_text="Portal quick actions list (JSON). Each item: label, url, icon, roles, enabled.",
    )
    portal_announcements = models.JSONField(
        default=default_portal_announcements,
        blank=True,
        help_text="Portal announcements list (JSON). Each item: title, meta, roles, enabled.",
    )
    portal_recent_grades = models.JSONField(
        default=default_portal_recent_grades,
        blank=True,
        help_text="Portal recent grades list (JSON). Each item: label, grade, tone, roles, enabled.",
    )
    portal_upcoming_assessments = models.JSONField(
        default=default_portal_upcoming_assessments,
        blank=True,
        help_text="Portal upcoming assessments list (JSON). Each item: title, when, detail, tone, roles, enabled.",
    )
    footer_accreditation_text = models.CharField(
        max_length=255,
        blank=True,
        default="Education platform ready for regional accreditation and global compliance",
        help_text="Footer accreditation text.",
    )
    footer_accreditation_subtext = models.CharField(
        max_length=255,
        blank=True,
        default="Certified for educational institutions worldwide | ISO 9001:2015 Quality Management",
        help_text="Footer accreditation subtext.",
    )
    footer_support_hours = models.CharField(
        max_length=120,
        blank=True,
        default="Mon-Fri: 8AM-6PM | Sat: 9AM-4PM",
        help_text="Footer support hours label.",
    )
    footer_whatsapp_url = models.URLField(
        blank=True,
        default="https://wa.me/237XXXXXXXXX?text=Hello%20School%20Management%20System%20Support",
        help_text="Footer WhatsApp support link.",
    )
    whatsapp_support_number = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Official WhatsApp Business number for general support (E.164 format, "
            "e.g. +2376XXXXXXX). If set, footer and portal can generate wa.me links."
        ),
    )
    whatsapp_admissions_number = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Optional WhatsApp Business number for Admissions / Front office. "
            "Used for admissions-specific CTAs when configured."
        ),
    )
    enable_whatsapp_parent_portal = models.BooleanField(
        default=False,
        help_text="Allow WhatsApp contact buttons in the parent portal (support and, if set, admissions).",
    )
    enable_whatsapp_staff_portal = models.BooleanField(
        default=False,
        help_text="Allow WhatsApp shortcuts for staff when contacting guardians.",
    )
    footer_status_text = models.CharField(
        max_length=120,
        blank=True,
        default="All Systems Operational",
        help_text="Footer system status label.",
    )
    footer_badges = models.JSONField(
        default=default_footer_badges,
        blank=True,
        help_text="Footer badges list (JSON). Each item: label, tone.",
    )
    footer_links = models.JSONField(
        default=default_footer_links,
        blank=True,
        help_text="Footer links list (JSON). Each item: label, url, roles, enabled.",
    )

    # Report preview & OCR configuration
    report_preview_contact_email = models.EmailField(
        blank=True,
        default="",
        help_text="Email shown on report card previews/header.",
    )
    report_preview_contact_phone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Phone number shown on report previews/header.",
    )
    report_preview_footer_note = models.CharField(
        max_length=160,
        blank=True,
        default="Powered by RunMyCampus.",
        help_text="Footer note text shown on report previews.",
    )
    default_report_preview_type = models.CharField(
        max_length=12,
        choices=[("term", "Term Report"), ("annual", "Annual Report")],
        default="term",
        help_text="Template shown to admins when opening a report preview from the builder.",
    )
    marksheet_ocr_command = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Absolute path to the Tesseract binary when the executable is not on PATH.",
    )

    # Grade approval workflow settings
    grade_approval_enabled = models.BooleanField(
        default=True,
        help_text="Require staff approval before publishing teacher-submitted marks.",
    )
    # Phase 4: MFA for compliance – require TOTP for selected roles (zero marginal cost)
    require_mfa_roles = models.JSONField(
        default=list,
        blank=True,
        help_text='Role codes that must have MFA (TOTP) enabled, e.g. ["ADMIN","BURSAR","IT_ADMIN"]. Empty = not required.',
    )
    require_mfa_all_staff = models.BooleanField(
        default=False,
        help_text="When enabled, all staff must set up MFA (TOTP) before accessing admin or backend. Overrides role-based require_mfa_roles for staff.",
    )
    # Phase 4.3: Optional reminder for pending AccessRequest assignees (0 = disabled)
    requests_reminder_interval_hours = models.PositiveIntegerField(
        default=0,
        blank=True,
        help_text="When > 0, a scheduled task notifies assignees of pending access requests (e.g. 24 = daily). 0 = disabled.",
    )
    grade_approval_roles = models.JSONField(
        default=default_grade_approval_roles,
        blank=True,
        help_text="List of role codes allowed to review/approve teacher grade submissions.",
    )
    grade_approval_auto_validate = models.BooleanField(
        default=True,
        help_text="Automatically flag missing or anomalous scores before sending to approvers.",
    )
    grade_approval_deadline_days = models.PositiveSmallIntegerField(
        default=3,
        help_text="Days before a submitted request must be reviewed.",
    )
    grade_approval_deadline_note = models.CharField(
        max_length=160,
        blank=True,
        default="Please review before the deadline.",
        help_text="Friendly reminder shown when deadline approaches.",
    )
    grade_post_roles = models.JSONField(
        default=default_grade_post_roles,
        blank=True,
        help_text="Roles that can finalize/post grade approvals (post/extract).",
    )
    syllabus_approval_roles = models.JSONField(
        default=default_syllabus_approval_roles,
        blank=True,
        help_text="List of role codes allowed to approve syllabi (e.g. DEAN, HOD). Used with delegation: when approver is OOO, their delegate receives requests.",
    )

    # Delegation (Out of Office / Acting) – configurable from admin
    delegation_max_days = models.PositiveSmallIntegerField(
        default=14,
        help_text="Maximum duration in days for a single delegation period.",
    )
    delegation_auto_revoke = models.BooleanField(
        default=True,
        help_text="When True, proxy access is automatically revoked at end of return date.",
    )
    delegation_notify_delegate_on_start = models.CharField(
        max_length=20,
        choices=[
            ("off", "Off"),
            ("email", "Email"),
            ("sms", "SMS"),
            ("both", "Email and SMS"),
        ],
        default="email",
        help_text="Notify the delegate when a delegation starts.",
    )
    delegation_block_delegator_while_ooo = models.BooleanField(
        default=True,
        help_text="When True, block the delegator from taking delegated actions while OOO (avoid double-approvals).",
    )
    delegation_role_mapping = models.JSONField(
        default=default_delegation_role_mapping,
        blank=True,
        help_text="Who can delegate to whom: {\"PRINCIPAL\": [\"VICE_PRINCIPAL\", \"HOD\"], ...}. Empty or missing role = no restriction.",
    )
    delegation_summary_report_on_return = models.BooleanField(
        default=True,
        help_text="When True, generate 'While You Were Away' summary for the returning user when delegation ends.",
    )

    # Feature toggles
    enable_parent_portal = models.BooleanField(default=True)
    enable_teacher_portal = models.BooleanField(default=True)
    DEFAULT_PORTAL_ROLE_DUAL_CHOICES = [
        ("", "Use primary role (user.role)"),
        ("TEACHER", "Teacher"),
        ("PARENT", "Parent"),
    ]
    default_portal_role_dual_role = models.CharField(
        max_length=20,
        choices=DEFAULT_PORTAL_ROLE_DUAL_CHOICES,
        blank=True,
        default="",
        help_text="For users who have both Teacher and Parent roles: default portal view when they have not yet chosen. Leave blank to use the user's primary role.",
    )
    enable_reports_pdf = models.BooleanField(default=True)
    report_downloads_enabled = models.BooleanField(default=True)
    # Phase 2: Evals–Reports – require approved grades before publish; report cards show only approved grades
    reports_require_approved_grades_before_publish = models.BooleanField(
        default=False,
        help_text="When enabled (and grade approval is on), block or warn when publishing term results if there are pending grade approvals.",
    )
    reports_use_approved_grades_only = models.BooleanField(
        default=False,
        help_text="When enabled, term/annual report context only includes evaluations whose subject has been approved (or has no approval request).",
    )
    portal_features = models.JSONField(default=default_portal_features, blank=True)
    social_links = models.JSONField(default=default_social_links, blank=True)
    backend_feature_flags = models.JSONField(
        default=default_backend_feature_flags,
        blank=True,
        help_text="Backend/front-office admin feature flags (entity console/import, schema UI, bulk limits).",
    )
    default_term_report_style = models.ForeignKey(
        "siteconfig.ReportCardStyle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="term_default_for",
    )
    default_annual_report_style = models.ForeignKey(
        "siteconfig.ReportCardStyle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="annual_default_for",
    )
    referral_bonus_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Default credit amount awarded per successful referral.",
    )
    
    # ===== NEW: GRADING CONFIGURATION =====
    default_grading_scale = models.CharField(
        max_length=50,
        choices=[
            ('numeric_0_20', 'Numeric 0–20 (Cameroon Francophone)'),
            ('letter_a_e', 'Letters A–E (Cameroon Anglophone)'),
            ('gpa_4_0', 'GPA 4.0 Scale'),
            ('percentage', 'Percentage 0–100'),
        ],
        default='numeric_0_20'
    )
    default_region = models.CharField(
        max_length=50,
        choices=[
            ('cameroon_anglophone', 'Cameroon Anglophone'),
            ('cameroon_francophone', 'Cameroon Francophone'),
            ('global', 'Global/Other'),
        ],
        default='cameroon_anglophone'
    )
    
    # ===== NEW: NOTIFICATIONS =====
    sms_provider = models.CharField(
        max_length=30,
        choices=[
            ('twilio', 'Twilio'),
            ('africastalking', 'AfricasTalking'),
            ('console', 'Console (Dev Only)'),
        ],
        default='console'
    )
    sms_api_key = models.CharField(max_length=255, blank=True)
    sms_sender_id = models.CharField(max_length=50, default="RUNMYCAMPUS")
    email_from_address = models.EmailField(default='noreply@school.example.com')
    
    # ===== NEW: DEADLINE REMINDERS =====
    teacher_deadline_reminder_days = models.JSONField(
        default=list,
        help_text="Days before deadline: [7, 3, 1, 0.5]"
    )
    teacher_reminder_time_of_day = models.TimeField(default='08:00')
    
    # ===== NEW: PERFORMANCE =====
    cache_rankings_interval_minutes = models.PositiveIntegerField(default=10)
    enable_concurrent_mark_uploads = models.BooleanField(default=True)
    
    # ===== NEW: PRACTICAL ASSESSMENT =====
    enable_practical_assessment = models.BooleanField(default=True)
    auto_tag_photos_from_exif = models.BooleanField(default=True)
    
    # ===== NEW: OFFLINE MODE =====
    enable_offline_mode = models.BooleanField(default=True)
    offline_sync_conflict_resolution = models.CharField(
        max_length=20,
        choices=[
            ('show_both', 'Show Both Versions'),
            ('reject', 'Reject Offline Entry'),
            ('auto_merge', 'Auto-Merge Latest'),
        ],
        default='show_both'
    )

    # Compliance profile (finance/payroll). Store the tenant model PK only so the
    # shared SiteSettings row does not carry a tenant ORM relation in schema mode.
    compliance_profile_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_column="compliance_profile_id",
        editable=False,
    )
    
    # ===== NEW: FINANCE AUTOMATION =====
    # Fee Invoice Generation
    finance_auto_generate_invoices_enabled = models.BooleanField(
        default=False,
        help_text="Enable automatic fee invoice generation based on schedule."
    )
    finance_auto_generate_schedule = models.JSONField(
        default=dict,
        blank=True,
        help_text='Schedule configuration: {"mode": "academic_year_start", "days_before": 7, "academic_year_start_offset_days": 0, "term_start_offset_days": 0, "custom_date": null}'
    )
    finance_auto_generate_due_date_offset_days = models.PositiveIntegerField(
        default=30,
        help_text="Days after issue date to set invoice due date."
    )
    finance_auto_generate_require_approval = models.BooleanField(
        default=False,
        help_text="Require admin approval before generating invoices automatically."
    )
    
    # Fee Plan Copying
    finance_fee_plan_auto_copy_enabled = models.BooleanField(
        default=False,
        help_text="Enable automatic fee plan copying on academic year transition."
    )
    finance_fee_plan_auto_copy_mode = models.CharField(
        max_length=20,
        choices=[
            ("manual", "Manual (admin action only)"),
            ("year_start", "Auto-copy on academic year start"),
            ("year_end", "Auto-copy on previous year end"),
        ],
        default="manual",
        help_text="When to automatically copy fee plans."
    )
    finance_fee_plan_copy_increase_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percentage increase to apply when copying fee plans (e.g., 5.00 for 5% increase)."
    )
    
    # Payment Reminders
    finance_payment_reminder_default_channels = models.JSONField(
        default=list,
        blank=True,
        help_text="Default notification channels for payment reminders: ['email'], ['whatsapp'], ['email', 'sms'], etc."
    )
    finance_payment_reminder_default_days = models.JSONField(
        default=list,
        blank=True,
        help_text="Default reminder days before due date: [7, 3, 1]"
    )
    finance_payment_reminder_enable_whatsapp = models.BooleanField(
        default=False,
        help_text="Enable WhatsApp as a payment reminder channel."
    )
    
    # Invoice Status Updates
    finance_invoice_auto_status_updates_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic invoice status updates (overdue, paid detection)."
    )
    finance_invoice_overdue_grace_period_days = models.PositiveIntegerField(
        default=0,
        help_text="Grace period in days before marking invoice as overdue."
    )
    
    # Receipt Verification & Automation
    finance_receipt_upload_enabled = models.BooleanField(
        default=True,
        help_text="Enable receipt upload in parent portal for cash/bank payments."
    )
    finance_receipt_auto_verify_enabled = models.BooleanField(
        default=True,
        help_text="Automatically verify uploaded receipts using pattern matching or OCR."
    )
    finance_receipt_verification_method = models.CharField(
        max_length=30,
        choices=[
            ("pattern", "Pattern Matching (Free)"),
            ("ocr_tesseract", "Tesseract OCR (Free, requires installation)"),
            ("ocr_cloud_google", "Google Vision API (Paid)"),
            ("ocr_cloud_aws", "AWS Textract (Paid)"),
        ],
        default="pattern",
        help_text="Method used to extract data from receipts."
    )
    finance_receipt_auto_apply_threshold = models.FloatField(
        default=0.9,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Confidence threshold (0.0-1.0) for auto-applying payments. Lower = more automatic, Higher = more manual review."
    )
    finance_receipt_auto_apply_enabled = models.BooleanField(
        default=True,
        help_text="Automatically apply payments when verification confidence exceeds threshold."
    )
    finance_receipt_require_admin_approval = models.BooleanField(
        default=False,
        help_text="Require admin approval even if verification passes (for extra security)."
    )
    finance_receipt_amount_tolerance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Tolerance for amount matching (e.g., 1.00 XAF difference allowed)."
    )
    
    # Bank Deposit Verification
    finance_bank_verification_enabled = models.BooleanField(
        default=True,
        help_text="Enable bank deposit verification against bank statements."
    )
    finance_bank_verification_auto_approve = models.BooleanField(
        default=False,
        help_text="Automatically approve receipts that are verified in bank statements."
    )
    finance_bank_verification_tolerance_days = models.PositiveIntegerField(
        default=7,
        help_text="Days to search before/after receipt date when matching bank statements."
    )
    finance_bank_verification_amount_tolerance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Amount tolerance when matching by amount + date (default: 1.00 XAF)."
    )
    
    # Payment Instructions for Reminders
    finance_payment_instructions_bank = models.TextField(
        blank=True,
        default=(
            "🏦 BANK TRANSFER:\n"
            "Account: {bank_account}\n"
            "Bank: {bank_name}\n"
            "Branch: {branch}\n"
            "Reference: {payment_code}"
        ),
        help_text="Bank transfer payment instructions template. Variables: {bank_account}, {bank_name}, {branch}, {payment_code}"
    )
    finance_payment_instructions_mtn_momo = models.TextField(
        blank=True,
        default=(
            "📱 MTN MOBILE MONEY:\n"
            "Merchant: {mtn_momo_number}\n"
            "Payment Code: {payment_code}\n"
            "Amount: {amount} XAF"
        ),
        help_text="MTN MoMo payment instructions template. Variables: {mtn_momo_number}, {payment_code}, {amount}"
    )
    finance_payment_instructions_orange_money = models.TextField(
        blank=True,
        default=(
            "📱 ORANGE MONEY:\n"
            "Merchant: {orange_money_number}\n"
            "Payment Code: {payment_code}\n"
            "Amount: {amount} XAF"
        ),
        help_text="Orange Money payment instructions template. Variables: {orange_money_number}, {payment_code}, {amount}"
    )
    finance_payment_instructions_cash = models.TextField(
        blank=True,
        default="💵 CASH: Pay at school office during business hours.",
        help_text="Cash payment instructions template"
    )
    finance_receipt_upload_instructions = models.TextField(
        blank=True,
        default="After payment, upload your receipt here: {receipt_upload_link}",
        help_text="Receipt upload instructions. Variables: {receipt_upload_link}"
    )

    # Real-world scenarios: reminders & receipt upload
    finance_reminder_no_contact_action = models.CharField(
        max_length=20,
        choices=[
            ("skip", "Skip reminder only"),
            ("warn_only", "Log warning only"),
            ("create_task", "Create task for staff to contact guardian"),
        ],
        default="warn_only",
        help_text="When guardian has no email/phone for reminder."
    )
    finance_receipt_max_size_mb = models.PositiveSmallIntegerField(
        default=5,
        help_text="Max receipt file size in MB (e.g. 5)."
    )
    finance_receipt_allowed_extensions = models.CharField(
        max_length=80,
        default="pdf,jpg,jpeg,png",
        help_text="Comma-separated: pdf,jpg,jpeg,png"
    )
    finance_overpayment_handling = models.CharField(
        max_length=30,
        choices=[
            ("reject", "Reject (strict)"),
            ("allow_with_refund", "Allow and create refund request for excess"),
            ("allow_as_credit", "Allow excess as credit for next invoice"),
        ],
        default="allow_with_refund",
        help_text="When receipt amount exceeds invoice balance."
    )
    finance_overpayment_tolerance_xaf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("1000.00"),
        help_text="Max overpayment to allow, in site default currency (Region config). Above this always flag for review."
    )
    finance_void_invoice_with_payments = models.CharField(
        max_length=30,
        choices=[
            ("allow", "Allow void, stop reminders only"),
            ("allow_credit_only", "Allow void, treat remaining as credit"),
            ("block_void", "Block void if invoice has payments"),
        ],
        default="allow",
        help_text="When voiding an invoice that has payments."
    )
    finance_on_student_withdrawal = models.CharField(
        max_length=30,
        choices=[
            ("stop_reminders_only", "Stop payment reminders only"),
            ("stop_and_mark", "Stop reminders and mark invoices (no new payments)"),
            ("no_auto_change", "No automatic change"),
        ],
        default="stop_reminders_only",
        help_text="When student is marked withdrawn/inactive."
    )
    finance_receipt_idempotency_window_minutes = models.PositiveSmallIntegerField(
        default=10,
        help_text="Minutes within which duplicate receipt upload (same invoice+user+file) is ignored."
    )
    finance_reminder_retry_failed_hours = models.PositiveSmallIntegerField(
        default=24,
        help_text="Retry failed reminders after this many hours (0 = no retry)."
    )
    finance_reminder_max_retries = models.PositiveSmallIntegerField(
        default=2,
        help_text="Max retries for failed reminder sends."
    )
    finance_receipt_require_verification_reason = models.BooleanField(
        default=True,
        help_text="Require a reason when staff manually approve or reject a receipt."
    )
    finance_receipt_second_approval_threshold_xaf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Receipts above this amount (site default currency, Region config) require second approver (0 = disabled)."
    )
    # Phase 2: Notifications to guardians (in-app + optional email)
    finance_notify_guardians_new_invoice = models.BooleanField(
        default=True,
        help_text="When a new invoice is issued, send in-app notification to guardians with finance access."
    )
    finance_notify_guardians_payment_received = models.BooleanField(
        default=True,
        help_text="When a payment is recorded, send in-app notification to guardians with finance access."
    )
    finance_notify_new_invoice_email = models.BooleanField(
        default=False,
        help_text="Also send email when a new invoice is issued (in addition to in-app notification)."
    )
    finance_notify_payment_received_email = models.BooleanField(
        default=False,
        help_text="Also send email when a payment is recorded (in addition to in-app notification)."
    )
    # Phase 2.1: Optional parent welcome email when parent account is created (backend or onboarding)
    notify_parent_welcome_email = models.BooleanField(
        default=False,
        help_text="When a parent account is created (e.g. from backend student create), send a short welcome email. Parent must contact school for login credentials unless you use a separate invite flow."
    )

    class DeadlineMode(models.TextChoices):
        TERM_END = "TERM_END", "Term end date"
        CUSTOM_DEADLINE = "CUSTOM_DEADLINE", "Custom deadline"
        PUBLISH_DATE = "PUBLISH_DATE", "Publish date"

    # Analytics defaults
    top_students_default_limit = models.PositiveSmallIntegerField(
        default=10,
        help_text=(
            "How many top students to show by default on analytics views "
            "(e.g. Top 10 students in a class or school)."
        ),
    )
    pass_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        help_text=(
            "Default pass mark used by analytics and summary widgets when a more "
            "specific rule is not configured."
        ),
    )
    use_promotion_rule_for_pass = models.BooleanField(
        default=False,
        help_text=(
            "If enabled, use the promotion rule configuration to decide pass/fail "
            "instead of this simple pass mark."
        ),
    )
    weak_subject_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        help_text=(
            "Score threshold below which a subject is highlighted as weak in "
            "analytics reports."
        ),
    )
    improvement_delta_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        help_text=(
            "Minimum score improvement required between terms for a student to be "
            "flagged as 'improving' in analytics."
        ),
    )
    deadline_mode = models.CharField(
        max_length=20,
        choices=DeadlineMode.choices,
        default=DeadlineMode.TERM_END,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    @classmethod
    def _ensure_preview_columns(cls) -> None:
        with connection.cursor() as cursor:
            try:
                columns = [col.name for col in connection.introspection.get_table_description(cursor, cls._meta.db_table)]
            except OperationalError:
                try:
                    connection.rollback()
                except DatabaseError:
                    pass
                return

            if "video_background" not in columns:
                try:
                    cursor.execute(
                        f'ALTER TABLE "{cls._meta.db_table}" ADD COLUMN "video_background" VARCHAR(255)'
                    )
                except OperationalError:
                    try:
                        connection.rollback()
                    except DatabaseError:
                        pass
                    pass

    @classmethod
    def _run_in_public_schema_if_tenant(cls, fn):
        """Run fn() in public schema when current connection is a tenant schema (siteconfig is shared-app only)."""
        schema_name = getattr(connection, "schema_name", None)
        if schema_name and schema_name != "public":
            try:
                from django_tenants.utils import schema_context
                with schema_context("public"):
                    return fn()
            except ImportError:
                pass
        return fn()

    @classmethod
    def get_solo(cls) -> "SiteSettings":
        global _SITE_SETTINGS_CACHE

        def _get_solo_impl():
            cls._ensure_preview_columns()
            if _SITE_SETTINGS_CACHE is None:
                obj, _ = cls.objects.get_or_create(pk=1)
                obj._sanitize_foreign_keys(persist=True)
                return obj
            try:
                _SITE_SETTINGS_CACHE.refresh_from_db()
                _SITE_SETTINGS_CACHE._sanitize_foreign_keys(persist=True)
                return _SITE_SETTINGS_CACHE
            except cls.DoesNotExist:
                obj, _ = cls.objects.get_or_create(pk=1)
                obj._sanitize_foreign_keys(persist=True)
                return obj
            except DatabaseError:
                return _SITE_SETTINGS_CACHE

        _SITE_SETTINGS_CACHE = cls._run_in_public_schema_if_tenant(_get_solo_impl)
        return _SITE_SETTINGS_CACHE

    def _sanitize_foreign_keys(self, *, persist: bool = False) -> list[str]:
        fk_guards = (
            ("theme_pack", "siteconfig", "ThemePack"),
            ("admin_theme_pack", "siteconfig", "ThemePack"),
            ("teacher_theme_pack", "siteconfig", "ThemePack"),
            ("parent_theme_pack", "siteconfig", "ThemePack"),
            ("default_term_report_style", "siteconfig", "ReportCardStyle"),
            ("default_annual_report_style", "siteconfig", "ReportCardStyle"),
            ("compliance_profile", "finance", "ComplianceProfile"),
        )
        model_cache: dict[tuple[str, str], object | None] = {}
        cleared_fields: list[str] = []

        for field_name, app_label, model_name in fk_guards:
            field_id = getattr(self, f"{field_name}_id", None)
            if not field_id:
                continue
            cache_key = (app_label, model_name)
            if cache_key not in model_cache:
                try:
                    model_cache[cache_key] = django_apps.get_model(app_label, model_name)
                except (LookupError, OperationalError):
                    model_cache[cache_key] = None
            related_model = model_cache[cache_key]
            if related_model is None:
                continue
            try:
                exists = related_model.objects.filter(pk=field_id).exists()
            except (OperationalError, DatabaseError):
                continue
            if exists:
                continue
            setattr(self, f"{field_name}_id", None)
            self._state.fields_cache.pop(field_name, None)
            cleared_fields.append(field_name)

        if persist and cleared_fields and getattr(self, "pk", None):
            update_kwargs = {f"{field_name}_id": None for field_name in cleared_fields}
            try:
                type(self).objects.filter(pk=self.pk).update(**update_kwargs)
            except (OperationalError, DatabaseError):
                pass

        return cleared_fields

    def get_theme_background(self, field_name: str) -> FieldFile | None:
        target = getattr(self, field_name, None)
        if target:
            return target
        theme = self.active_theme
        if theme and hasattr(theme, field_name):
            return getattr(theme, field_name)
        return None

    def get_theme_logo_opacity(self) -> float:
        if self.logo_opacity not in (None, ""):
            return self.logo_opacity
        theme = self.active_theme
        if theme and theme.logo_opacity not in (None, ""):
            return theme.logo_opacity
        return 0.3

    def get_theme_logo_bg_mode(self) -> str:
        if self.logo_background_mode:
            return self.logo_background_mode
        theme = self.active_theme
        if theme and getattr(theme, "logo_background_mode", None):
            return theme.logo_background_mode
        return "contain"

    def save(self, *args, **kwargs):
        cleared_fields = self._sanitize_foreign_keys()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and cleared_fields:
            normalized_update_fields = set(update_fields)
            normalized_update_fields.update(cleared_fields)
            kwargs["update_fields"] = list(normalized_update_fields)
        super().save(*args, **kwargs)

    @property
    def compliance_profile(self):
        profile_id = getattr(self, "compliance_profile_id", None)
        if not profile_id:
            self._state.fields_cache["compliance_profile"] = None
            return None
        cached = self._state.fields_cache.get("compliance_profile")
        if cached is not None and getattr(cached, "pk", None) == profile_id:
            return cached
        try:
            compliance_model = django_apps.get_model("finance", "ComplianceProfile")
        except LookupError:
            return None
        try:
            profile = compliance_model.objects.filter(pk=profile_id).first()
        except (OperationalError, DatabaseError):
            return None
        self._state.fields_cache["compliance_profile"] = profile
        return profile

    @compliance_profile.setter
    def compliance_profile(self, value):
        if value is None:
            self.compliance_profile_id = None
            self._state.fields_cache["compliance_profile"] = None
            return
        profile_id = getattr(value, "pk", value)
        self.compliance_profile_id = profile_id or None
        self._state.fields_cache["compliance_profile"] = value if getattr(value, "pk", None) else None

    @property
    def active_theme(self) -> "ThemePack | None":
        if self.theme_pack_id:
            try:
                selected = ThemePack.objects.filter(pk=self.theme_pack_id).first()
            except (OperationalError, DatabaseError):
                return None
            if selected:
                self._state.fields_cache["theme_pack"] = selected
                return selected
            self._sanitize_foreign_keys(persist=True)
        try:
            fallback = ThemePack.objects.filter(is_default=True, is_active=True).first()
            if fallback:
                return fallback
            return ThemePack.objects.filter(is_active=True).order_by("name").first()
        except (OperationalError, DatabaseError):
            return None

    def apply_theme_pack(self, pack: "ThemePack", save: bool = True) -> None:
        self.theme_pack = pack
        self.primary_color = pack.primary_color
        self.accent_color = pack.accent_color
        self.custom_css = pack.custom_css or ""
        self.brand_font = pack.font_family or self.brand_font
        update_fields = ["theme_pack", "primary_color", "accent_color", "custom_css", "brand_font"]
        if save:
            self.save(update_fields=update_fields)

    @property
    def active_social_links(self) -> list[dict]:
        links = []
        for item in self.social_links or []:
            if not item.get("enabled"):
                continue
            url = item.get("url")
            if not url:
                continue
            links.append(item)
        return links

    def get_admin_theme(self):
        if self.admin_theme_pack_id:
            try:
                admin_pack = ThemePack.objects.filter(pk=self.admin_theme_pack_id).first()
            except (OperationalError, DatabaseError):
                admin_pack = None
            if admin_pack and admin_pack.is_active and admin_pack.applies_to_admin:
                self._state.fields_cache["admin_theme_pack"] = admin_pack
                return admin_pack
            if admin_pack is None:
                self._sanitize_foreign_keys(persist=True)

        site_pack = None
        if self.theme_pack_id:
            try:
                site_pack = ThemePack.objects.filter(pk=self.theme_pack_id).first()
            except (OperationalError, DatabaseError):
                site_pack = None
            if site_pack and site_pack.is_active and getattr(site_pack, "applies_to_admin", False):
                self._state.fields_cache["theme_pack"] = site_pack
                return site_pack
            if site_pack is None:
                self._sanitize_foreign_keys(persist=True)
        try:
            fallback = ThemePack.objects.filter(applies_to_admin=True, is_active=True).order_by("-is_default", "name").first()
            return fallback or site_pack
        except (OperationalError, DatabaseError):
            return site_pack

    def get_portal_theme(self, user=None, effective_role: str | None = None) -> "ThemePack | None":
        """
        Return the theme pack for the portal (role-based when per-role packs are set).
        effective_role should be TEACHER or PARENT from get_effective_portal_role(request).
        If effective_role is TEACHER and teacher_theme_pack is set, use it; if PARENT and
        parent_theme_pack is set, use it; otherwise use active_theme (portal theme pack).
        """
        role = (effective_role or "").strip().upper() or (
            getattr(user, "role", "") or ""
        ).strip().upper() if user and getattr(user, "is_authenticated", False) else ""
        if role == "TEACHER" and self.teacher_theme_pack_id:
                try:
                    pack = ThemePack.objects.filter(
                        pk=self.teacher_theme_pack_id, is_active=True
                    ).first()
                    if pack:
                        return pack
                except (OperationalError, DatabaseError):
                    pass
        if role == "PARENT" and self.parent_theme_pack_id:
                try:
                    pack = ThemePack.objects.filter(
                        pk=self.parent_theme_pack_id, is_active=True
                    ).first()
                    if pack:
                        return pack
                except (OperationalError, DatabaseError):
                    pass
        return self.active_theme


class ThemePack(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    background_color = models.CharField(max_length=20, default="#ffffff")
    font_family = models.CharField(max_length=120, default="Inter, system-ui, sans-serif")
    layout = models.CharField(max_length=20, choices=ThemeLayout.choices, default=ThemeLayout.STANDARD)
    custom_css = models.TextField(blank=True)
    palette = models.JSONField(default=dict, blank=True)
    logo = models.ImageField(upload_to="branding/themepack/logo/", blank=True, null=True, help_text="Optional: Logo for this theme pack.")
    background_image = models.ImageField(upload_to="branding/themepack/bg/", blank=True, null=True, help_text="Optional: Background image for this theme pack.")
    video_background = models.FileField(upload_to="branding/themepack/video/", blank=True, null=True, help_text="Optional: Video background for this theme pack.")
    svg_background = models.FileField(upload_to="branding/themepack/svg/", blank=True, null=True, help_text="Optional: SVG background for this theme pack.")
    logo_opacity = models.FloatField(default=0.3, blank=True, null=True, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)], help_text="Opacity for theme logo background (0.0 = transparent, 1.0 = opaque)")
    logo_background_mode = models.CharField(max_length=16, choices=SiteSettings.LOGO_BG_MODE_CHOICES, default="contain", help_text="How the theme logo background image is displayed.")
    applies_to_admin = models.BooleanField(
        default=False,
        help_text="Use this pack for the Django /admin interface.",
    )
    backend_console_theme = models.CharField(
        max_length=20,
        choices=SiteSettings.BACKEND_CONSOLE_THEME_CHOICES,
        blank=True,
        default="",
        help_text="Optional: When set, this pack's console mode (light/dark) is used for /backend and /admin. Leave blank to use the site-level Backend console theme.",
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                condition=Q(is_default=True),
                fields=("is_default",),
                name="siteconfig_one_default_themepack",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        # Optimize logo
        if self.logo and hasattr(self.logo, 'file') and not getattr(self.logo.file, '_optimized', False):
            optimized = optimize_image(self.logo)
            if optimized:
                optimized._optimized = True
                self.logo.save(self.logo.name, optimized, save=False)
        # Optimize background image
        if self.background_image and hasattr(self.background_image, 'file') and not getattr(self.background_image.file, '_optimized', False):
            optimized = optimize_image(self.background_image)
            if optimized:
                optimized._optimized = True
                self.background_image.save(self.background_image.name, optimized, save=False)
        if self.is_default:
            ThemePack.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def gradient_colors(self) -> tuple[str, str]:
        gradient = (self.palette or {}).get("gradient", [])
        if len(gradient) >= 2:
            return gradient[0], gradient[1]
        return self.primary_color, self.accent_color

    def preview_style(self) -> str:
        start, end = self.gradient_colors
        return f"background: linear-gradient(135deg, {start}, {end}); color: white;"


class Integration(models.Model):
    """
    Unified external integration: plugin config + API Center governance (one module).
    Examples: Email (SMTP), SMS (Twilio), Payments (MTN MoMo), Analytics.
    Single kill switch: enabled. Optional governance: rate limit, scopes, audit via IntegrationAuditLog.
    """

    PROVIDERS = [
        ("email", "Email"),
        ("sms", "SMS"),
        ("payments", "Payments"),
        ("analytics", "Analytics"),
        ("whatsapp", "WhatsApp Business"),
        ("push", "Push Notifications"),
        ("stripe", "Stripe"),
        ("badges", "Digital Badges"),
        ("lms", "LMS"),
        ("other", "Other"),
    ]

    CATEGORIES = [
        ("LMS", "LMS"),
        ("PAYMENT", "Payment"),
        ("ATTENDANCE", "Attendance"),
        ("LIBRARY", "Library"),
        ("AI", "AI"),
        ("SIS", "SIS"),
        ("MESSAGING", "Messaging"),
        ("BADGES", "Badges"),
        ("BILLING", "Billing"),
        ("OTHER", "Other"),
    ]

    HEALTH_STATUS = [
        ("healthy", "Healthy"),
        ("degraded", "Degraded"),
        ("down", "Down"),
    ]

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=50, unique=True)
    provider = models.CharField(max_length=30, choices=PROVIDERS, default="other")
    category = models.CharField(max_length=20, choices=CATEGORIES, default="OTHER", blank=True)
    enabled = models.BooleanField(
        default=False,
        help_text="Master kill switch: when False, this integration is not used (payments, email, portal links).",
    )
    config = models.JSONField(default=dict, blank=True)
    # Governance: rate limit, scopes, audit (toggle in API Center)
    rate_limit_per_min = models.PositiveIntegerField(null=True, blank=True)
    ip_whitelist = models.JSONField(default=list, blank=True)
    allowed_scopes = models.JSONField(default=dict, blank=True)
    secret_key_hash = models.TextField(blank=True)
    last_call_at = models.DateTimeField(null=True, blank=True)
    health_status = models.CharField(max_length=20, choices=HEALTH_STATUS, default="healthy", blank=True)
    pii_masking = models.BooleanField(default=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="integrations",
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.provider})"


class UserPreference(models.Model):
    class NotificationChannel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        APP = "APP", "App"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    timezone = models.CharField(max_length=64, default=settings.TIME_ZONE)
    dashboard_view = models.CharField(
        max_length=20,
        choices=DashboardView.choices,
        default=DashboardView.OVERVIEW,
    )
    refresh_rate_minutes = models.PositiveSmallIntegerField(default=60)
    notification_channels = models.JSONField(default=list, blank=True)
    receive_weekly_summary = models.BooleanField(default=True)
    dashboard_widgets = models.JSONField(default=list, blank=True)
    preferred_language = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="User's preferred UI language (e.g. en, fr). When set, overrides region default.",
    )
    preferred_region = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="User's preferred region code (e.g. CMR, USA). When set, drives currency, date format, grading.",
    )
    last_portal_role = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="For users with both Teacher and Parent roles: last selected portal view (TEACHER or PARENT). Restored on login.",
    )
    simple_mode = models.BooleanField(
        default=False,
        help_text="Plan XIV: When True, show simplified UI (consumer-grade).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"{self.user.username} preferences"


class FormDraft(models.Model):
    """
    Section 26.5: Save draft for long tenant-facing forms (application, onboarding, etc.).
    One draft per (school, user, form_key); data is JSON form state; updated_at for expiry.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="form_drafts",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="form_drafts",
    )
    form_key = models.CharField(
        max_length=80,
        db_index=True,
        help_text="Form identifier, e.g. backend_student_create, application_form.",
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Serialized form field values (safe to rehydrate into form).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "siteconfig"
        verbose_name = "Form draft"
        verbose_name_plural = "Form drafts"
        unique_together = [["school", "user", "form_key"]]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.form_key} ({self.user_id})"


REPORT_EXPORT_HANDLERS = {}


def report_exporter(slug):
    def decorator(fn):
        REPORT_EXPORT_HANDLERS[slug] = fn
        return fn
    return decorator


@report_exporter("students")
def _student_export():
    StudentProfile = django_apps.get_model("people", "StudentProfile")
    headers = [
        "Student Code",
        "Name",
        "Academic Year",
        "Classroom",
        "Specialty",
        "Active",
    ]
    rows = []
    qs = StudentProfile.objects.select_related("classroom", "specialty")
    for student in qs:
        rows.append(
            [
                student.student_code,
                f"{student.first_name} {student.last_name}",
                student.academic_year.name,
                student.classroom.name,
                student.specialty.name,
                "Yes" if student.is_active else "No",
            ]
        )
    return headers, rows


@report_exporter("teachers")
def _teacher_export():
    TeacherProfile = django_apps.get_model("people", "TeacherProfile")
    headers = ["Username", "Full Name", "Department", "Position", "Payment Method"]
    rows = []
    qs = TeacherProfile.objects.select_related("department", "user")
    for teacher in qs:
        rows.append(
            [
                teacher.user.username,
                teacher.user.get_full_name() or teacher.user.username,
                teacher.department.name if teacher.department else "",
                teacher.position_title,
                teacher.get_payment_method_display(),
            ]
        )
    return headers, rows


@report_exporter("subjects")
def _subject_export():
    headers = ["Subject", "Category"]
    rows = [[subject.name, subject.get_category_display()] for subject in Subject.objects.all()]
    return headers, rows


@report_exporter("fee_payments")
def _payment_export():
    Payment = django_apps.get_model("finance", "Payment")
    headers = ["Student", "Invoice", "Amount", "Method", "Paid At", "Receipt"]
    rows = []
    qs = Payment.objects.select_related("invoice__student")
    for payment in qs:
        student = payment.invoice.student
        student_name = student and f"{student.first_name} {student.last_name}" or "N/A"
        rows.append(
            [
                student_name,
                payment.invoice.reference or f"#{payment.invoice.id}",
                f"{payment.amount:.2f}",
                payment.get_method_display(),
                payment.paid_at.strftime("%Y-%m-%d %H:%M"),
                payment.receipt_number,
            ]
        )
    return headers, rows


class ReportTemplate(models.Model):
    class ReportFormat(models.TextChoices):
        CSV = "CSV", "CSV"
        PDF = "PDF", "PDF"
        EXCEL = "EXCEL", "Excel"
        ODS = "ODS", "LibreOffice (ODS)"

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    template_family = models.CharField(
        max_length=80,
        blank=True,
        help_text="Optional: match EducationSystemProfile.config.report_template_family (e.g. global, cameroon, east_africa). Blank = show for all.",
    )
    is_active = models.BooleanField(default=True)
    preferred_format = models.CharField(
        max_length=10,
        choices=ReportFormat.choices,
        default=ReportFormat.CSV,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_export_data(self):
        handler = REPORT_EXPORT_HANDLERS.get(self.slug)
        if handler:
            return handler()
        return [], []

    def filename(self):
        return f"{self.slug}.{self.preferred_format.lower()}"


class OfficialReportTemplate(models.Model):
    """
    Uploadable report template per region/sub_system (Phase 2 template engine).
    MINESEC-style or custom HTML/Excel; data injection via placeholders.
    """
    class SubSystem(models.TextChoices):
        FR = "FR", "French sub-system"
        EN = "EN", "English sub-system"
        INT = "INT", "International"

    region_code = models.CharField(max_length=20, blank=True, help_text="e.g. CMR")
    sub_system = models.CharField(max_length=10, choices=SubSystem.choices, default=SubSystem.EN)
    name = models.CharField(max_length=120)
    template_file = models.FileField(
        upload_to="report_templates/official/",
        blank=True,
        null=True,
        help_text="HTML or Excel template for data injection",
    )
    version = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="official_report_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["region_code", "sub_system", "name"]

    def __str__(self):
        return f"{self.name} ({self.region_code}/{self.sub_system})"


class ReportCardStyleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ReportCardStyle(models.Model):
    class WatermarkMode(models.TextChoices):
        TEXT = "TEXT", "Text watermark"
        SITE_LOGO = "SITE_LOGO", "Use site logo"
        STYLE_LOGO = "STYLE_LOGO", "Use style logo"
        NONE = "NONE", "Disabled"

    class WatermarkPosition(models.TextChoices):
        CENTER = "CENTER", "Center"
        TOP_LEFT = "TOP_LEFT", "Top left"
        TOP_RIGHT = "TOP_RIGHT", "Top right"
        BOTTOM_LEFT = "BOTTOM_LEFT", "Bottom left"
        BOTTOM_RIGHT = "BOTTOM_RIGHT", "Bottom right"

    TERM_TEMPLATE_CHOICES = [
        ("reports/term_report.html", "Standard term template"),
        ("reports/term_report_cameroon.html", "Cameroon term template"),
        ("reports/term_report_cameroon_modern.html", "Cameroon term template (modern)"),
    ]
    ANNUAL_TEMPLATE_CHOICES = [
        ("reports/annual_report.html", "Standard annual template"),
        ("reports/annual_report_cameroon.html", "Cameroon annual template"),
        ("reports/annual_report_cameroon_modern.html", "Cameroon annual template (modern)"),
    ]

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    term_template = models.CharField(max_length=120, choices=TERM_TEMPLATE_CHOICES, default=TERM_TEMPLATE_CHOICES[0][0])
    annual_template = models.CharField(max_length=120, choices=ANNUAL_TEMPLATE_CHOICES, default=ANNUAL_TEMPLATE_CHOICES[0][0])
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    watermark_text = models.CharField(max_length=150, blank=True)
    watermark_mode = models.CharField(
        max_length=20,
        choices=WatermarkMode.choices,
        default=WatermarkMode.TEXT,
        help_text="Choose how watermark is rendered in report templates.",
    )
    watermark_logo = models.ImageField(
        upload_to="branding/reportcard/watermarks/",
        blank=True,
        null=True,
        help_text="Optional custom watermark logo used when mode is 'Use style logo'.",
    )
    watermark_opacity = models.FloatField(
        default=0.08,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Watermark opacity from 0.0 to 1.0.",
    )
    watermark_scale = models.PositiveSmallIntegerField(
        default=55,
        validators=[MinValueValidator(20), MaxValueValidator(180)],
        help_text="Watermark size as percentage (20-180).",
    )
    watermark_position = models.CharField(
        max_length=20,
        choices=WatermarkPosition.choices,
        default=WatermarkPosition.CENTER,
        help_text="Watermark placement in the report canvas.",
    )
    header_tagline = models.CharField(max_length=200, blank=True)
    css_snippet = models.TextField(blank=True)
    labels = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Key/value labels used by report templates for wording. "
            "Example: {\"report_title\": \"ACADEMIC REPORT SHEET\", \"rank\": \"Rank\"}."
        ),
    )
    layout_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Layout configuration for report templates (show/hide columns/sections). "
            "Example: {\"show_school_rank\": true, \"show_specialty_rank\": true}."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReportCardStyleQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def template_for(self, report_type: str) -> str:
        if report_type == REPORT_CARD_TYPE_TERM:
            return self.term_template
        return self.annual_template

    def label(self, key: str, default: str = "") -> str:
        """Safe label lookup for templates."""
        data = self.labels or {}
        value = data.get(key, default)
        return str(value) if value is not None else default

    def flag(self, key: str, default: bool = False) -> bool:
        """Safe boolean lookup for templates."""
        data = self.layout_config or {}
        value = data.get(key, default)
        return bool(value) if value is not None else bool(default)


from apps.academics.models import ReportCardStyleAssignment  # noqa: E402,F401

def get_report_card_style_for_student(student: StudentProfile, report_type: str) -> ReportCardStyle | None:
    if not student or not student.classroom:
        return None
    assignment = getattr(student.classroom, "report_card_style_assignment", None)
    if assignment and assignment.style and assignment.style.is_active:
        return assignment.style

    from apps.platform_runtime.helpers import get_effective_site_settings

    site = get_effective_site_settings(school=getattr(student, "school", None))
    default_field = "default_term_report_style" if report_type == REPORT_CARD_TYPE_TERM else "default_annual_report_style"
    style = getattr(site, default_field, None)
    if style and style.is_active:
        return style

    return ReportCardStyle.objects.active().first()


# ============================================================================
# Phase 1.2.4: Internationalization & Multi-Region Support
# ============================================================================

class RegionConfig(models.Model):
    """
    Store region-specific settings for schools worldwide.
    Enables deployment in any country with appropriate grading scales, currencies, timezones.
    """
    CALENDAR_CHOICES = [
        ('gregorian', 'Gregorian'),
        ('islamic', 'Islamic'),
        ('buddhist', 'Buddhist'),
        ('hebrew', 'Hebrew'),
    ]
    GRADING_SCALE_CHOICES = [
        ('0-20', 'Cameroon (0-20)'),
        ('0-100', 'US/UK (0-100)'),
        ('0-10', 'European (0-10)'),
        ('a-f', 'Letter Grade (A-F)'),
        ('gpa', 'GPA (0-4.0)'),
    ]
    
    code = models.CharField(
        max_length=10, 
        unique=True, 
        primary_key=True,
        help_text="ISO country code (CMR, USA, GBR, KEN, NGA, etc.)"
    )
    name = models.CharField(max_length=100, help_text="Country/Region name (Cameroon, United States, etc.)")
    
    # Localization settings
    default_language = models.CharField(
        max_length=10, 
        default='en',
        help_text="Default language code (en, fr, pid, sw, ha)"
    )
    timezone = models.CharField(
        max_length=50, 
        default='UTC',
        help_text="Timezone name (Africa/Douala, America/New_York, Europe/London, etc.)"
    )
    decimal_separator = models.CharField(max_length=1, default='.', help_text="Decimal separator (. or ,)")
    thousands_separator = models.CharField(max_length=1, default=',', help_text="Thousands separator (, or .)")
    date_format = models.CharField(
        max_length=20, 
        default='DD/MM/YYYY',
        help_text="Date display format (DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD)"
    )
    
    # Education system configuration
    calendar_system = models.CharField(
        max_length=20, 
        choices=CALENDAR_CHOICES, 
        default='gregorian'
    )
    grading_scale = models.CharField(
        max_length=20, 
        choices=GRADING_SCALE_CHOICES, 
        default='0-20'
    )
    default_currency = models.CharField(
        max_length=3, 
        default='XAF',
        help_text="ISO currency code (XAF, USD, EUR, GBP, KES, NGN, etc.)"
    )
    
    # Academic structure
    academic_year_start_month = models.IntegerField(
        default=9,
        help_text="Month when academic year starts (1-12, usually 9=September)"
    )
    term_count_per_year = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Number of instructional periods in a school year (1-12).",
    )
    # Global regional grading: report card / transcript average formula (e.g. simple average vs coefficient-based).
    # Cameroon and other systems use coefficient-based; store as {"type": "coefficient", "scale_max": 20} or {"type": "simple"}.
    grading_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text="Report card average: {\"type\": \"simple\"} or {\"type\": \"coefficient\", \"scale_max\": 20}. Subject coefficients from GradingScaleConfig or school settings.",
    )

    # Legal/compliance
    school_registration_number_format = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Regex pattern for school registration numbers"
    )
    student_id_format = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Format for student IDs (e.g., 'nnnn' for 4 digits)"
    )
    certificate_template_name = models.CharField(
        max_length=100, 
        default='standard',
        help_text="Certificate template to use (standard, fancy, minimal, etc.)"
    )
    
    # Portal features
    enable_online_admissions = models.BooleanField(
        default=True,
        help_text="Allow online applications in this region"
    )
    enable_parent_portal = models.BooleanField(
        default=True,
        help_text="Enable parent/guardian access to student information"
    )
    enable_student_portal = models.BooleanField(
        default=True,
        help_text="Enable student self-service portal"
    )
    is_rtl = models.BooleanField(
        default=False,
        help_text="Right-to-left script (Arabic, Hebrew, Urdu). When True, set <html dir=\"rtl\"> from tenant locale."
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Region Configurations"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def gradingscaleconfig_set(self):
        """
        Backwards-compatible alias for legacy code/tests expecting the
        default related manager name from GradingScaleConfig.
        """
        return self.grading_scales
    
    @classmethod
    def get_default(cls):
        """Get the platform-neutral fallback region, creating it if necessary."""
        region, _ = cls.objects.get_or_create(
            code='GLOBAL',
            defaults={
                'name': 'Global Default',
                'default_language': 'en',
                'timezone': getattr(settings, "TIME_ZONE", "UTC") or "UTC",
                'date_format': 'YYYY-MM-DD',
                'grading_scale': '0-100',
                'default_currency': 'USD',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            }
        )
        return region


def default_education_term_labels():
    return ["Term 1", "Term 2", "Term 3"]


def default_education_subject_seed():
    return [
        {"name": "Mathematics", "category": "GENERAL"},
        {"name": "English", "category": "GENERAL"},
        {"name": "Science", "category": "GENERAL"},
    ]


class EducationSystemProfile(models.Model):
    """
    Country/sub-system template used when provisioning a new school.
    Encodes curriculum defaults without hardcoding logic in tasks.
    """

    class SubSystem(models.TextChoices):
        ANY = "ANY", "Any"
        FR = "FR", "French sub-system"
        EN = "EN", "English sub-system"
        INT = "INT", "International"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_REVIEW = "IN_REVIEW", "In Review"
        APPROVED = "APPROVED", "Approved"
        DEPRECATED = "DEPRECATED", "Deprecated"

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    lineage_key = models.SlugField(
        max_length=80,
        blank=True,
        default="",
        help_text="Stable pack lineage key across versions (defaults to code for legacy packs).",
    )
    version = models.CharField(
        max_length=20,
        default="1.0.0",
        help_text="Semantic version for this pack (e.g. 1.0.0).",
    )
    region = models.ForeignKey(
        RegionConfig,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="education_profiles",
    )
    province = models.ForeignKey(
        "siteconfig.Province",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="education_profiles",
        help_text="Optional province/state for filtering systems by geography.",
    )
    sub_system = models.CharField(max_length=10, choices=SubSystem.choices, default=SubSystem.ANY)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_education_profiles",
    )

    academic_year_start_month = models.IntegerField(
        default=9,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    term_count_per_year = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    term_labels = models.JSONField(
        default=default_education_term_labels,
        blank=True,
        help_text='Ordered labels for terms/semesters (e.g. ["Term 1", "Term 2", "Term 3"]).',
    )
    grading_scale = models.CharField(max_length=20, default="0-100")
    default_language = models.CharField(max_length=10, default="en")
    default_currency = models.CharField(max_length=3, default="USD")
    default_timezone = models.CharField(max_length=64, default="UTC")
    subject_seed = models.JSONField(
        default=default_education_subject_seed,
        blank=True,
        help_text='Default subjects to seed when onboarding a school.',
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional profile settings (grading logic, compliance tags, etc.).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "code"]

    def __str__(self):
        scope = self.region.code if self.region_id else "GLOBAL"
        return f"{self.name} [{scope}/{self.sub_system}] v{self.version}"

    def save(self, *args, **kwargs):
        if not self.lineage_key:
            self.lineage_key = str(self.code or "").strip()
        super().save(*args, **kwargs)

    def normalized_term_labels(self) -> list[str]:
        labels = [str(item).strip() for item in (self.term_labels or []) if str(item).strip()]
        if len(labels) >= int(self.term_count_per_year or 0):
            return labels
        labels.extend([f"Term {idx + 1}" for idx in range(len(labels), int(self.term_count_per_year or 0))])
        return labels

    def normalized_subject_seed(self) -> list[dict]:
        rows = []
        for item in self.subject_seed or []:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    rows.append({"name": name, "category": "GENERAL"})
                continue
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                category = str(item.get("category") or "GENERAL").strip().upper() or "GENERAL"
                rows.append({"name": name, "category": category})
        if rows:
            return rows
        return default_education_subject_seed()

    @classmethod
    def for_school(cls, school):
        """
        Resolve the best profile for a school:
        region+subsystem > region+ANY > global+subsystem > global+ANY.
        """
        if school is None:
            return (
                cls.objects.filter(
                    is_active=True,
                    is_default=True,
                    approval_status=cls.ApprovalStatus.APPROVED,
                )
                .order_by("-approved_at", "-updated_at")
                .first()
            )
        sub_system = (getattr(school, "sub_system", "") or cls.SubSystem.ANY).upper()
        region_id = getattr(school, "default_region_id", None)
        matches = []
        if region_id:
            matches.append({"region_id": region_id, "sub_system": sub_system})
            matches.append({"region_id": region_id, "sub_system": cls.SubSystem.ANY})
        matches.append({"region__isnull": True, "sub_system": sub_system})
        matches.append({"region__isnull": True, "sub_system": cls.SubSystem.ANY})

        for cond in matches:
            profile = (
                cls.objects.filter(
                    is_active=True,
                    approval_status=cls.ApprovalStatus.APPROVED,
                    **cond,
                )
                .order_by("-is_default", "-approved_at", "name")
                .first()
            )
            if profile:
                return profile
        return None


# ============================================================================
# Global Powerhouse Phase A: Location hierarchy, TenantSystems, SystemFeatures
# ============================================================================


class Province(models.Model):
    """
    Optional Province/State under a country (RegionConfig).
    Used for geo-educational filtering in onboarding (e.g. systems by country + province).
    """
    region = models.ForeignKey(
        RegionConfig,
        on_delete=models.CASCADE,
        related_name="provinces",
        help_text="Country (region) this province belongs to.",
    )
    code = models.CharField(max_length=32, help_text="Province/state code (e.g. NW, CA)")
    name = models.CharField(max_length=120, help_text="Province/state name")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["region", "name"]
        unique_together = [("region", "code")]
        verbose_name = "Province / State"
        verbose_name_plural = "Provinces / States"

    def __str__(self):
        return f"{self.name} ({self.region.code})"


class TenantSystem(models.Model):
    """
    Junction: School ↔ EducationSystemProfile (many-to-many).
    A school can select multiple systems (e.g. General + Trade).
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="tenant_systems",
    )
    system = models.ForeignKey(
        EducationSystemProfile,
        on_delete=models.CASCADE,
        related_name="tenant_schools",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("school", "system")]
        ordering = ["school", "system"]
        verbose_name = "Tenant system assignment"
        verbose_name_plural = "Tenant system assignments"

    def __str__(self):
        return f"{self.school.name} ↔ {self.system.name}"


# ============================================================================
# Section 22: Tenant admission number policy (per-school config)
# ============================================================================


class TenantAdmissionNumberPolicy(models.Model):
    """
    Section 22.3: Per-school admission number generation policy.
    When present, overrides SiteSettings and school.settings["admissions"] for admission number config.
    """
    class Strategy(models.TextChoices):
        FULL = "FULL", "Full (YY+School+Seq+Spec+Class)"
        YEAR_SEQ = "YEAR_SEQ", "Year + sequence only"
        SEQ_ONLY = "SEQ_ONLY", "Sequence only"
        TEMPLATE = "TEMPLATE", "Custom template"

    class ResetFrequency(models.TextChoices):
        NEVER = "NEVER", "Never (global sequence)"
        YEARLY = "YEARLY", "Per academic year"
        TERM = "TERM", "Per term"

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="admission_number_policy",
    )
    strategy = models.CharField(
        max_length=20,
        choices=Strategy.choices,
        default=Strategy.FULL,
    )
    template = models.CharField(
        max_length=255,
        blank=True,
        help_text="Placeholders: {year_2digit}, {school_code}, {seq_4digit}, {spec_code}, {class_segment}. Overrides strategy when set.",
    )
    pattern = models.CharField(
        max_length=255,
        blank=True,
        help_text="Regex to validate admission numbers. Leave blank for default.",
    )
    school_code = models.CharField(max_length=20, default="SCH")
    seq_width = models.PositiveSmallIntegerField(default=4, help_text="Padding width for sequence (e.g. 4 → 0001).")
    reset_frequency = models.CharField(
        max_length=20,
        choices=ResetFrequency.choices,
        default=ResetFrequency.YEARLY,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant admission number policy"
        verbose_name_plural = "Tenant admission number policies"

    def __str__(self):
        return f"{self.school.name}: {self.get_strategy_display()}"


class SystemFeature(models.Model):
    """
    Feature key enabled by an education system template.
    getTenantModules() unions these for all systems assigned to a school.
    """
    system = models.ForeignKey(
        EducationSystemProfile,
        on_delete=models.CASCADE,
        related_name="system_features",
    )
    feature_key = models.CharField(
        max_length=80,
        help_text="Module/feature code (e.g. library, transport, workshop_management).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("system", "feature_key")]
        ordering = ["system", "feature_key"]
        verbose_name = "System feature"
        verbose_name_plural = "System features"

    def __str__(self):
        return f"{self.system.code}:{self.feature_key}"


# ============================================================================
# Global Powerhouse Phase D: Plan and feature gate (subscription logic)
# ============================================================================


class Plan(models.Model):
    """
    Subscription plan: max_students, max_staff, included_features.
    School.plan_id links to this; is_feature_enabled(tenant, code) considers plan + addons.
    """

    class BillingModel(models.TextChoices):
        FLAT = "FLAT", "Flat (fixed monthly)"
        PER_STUDENT = "PER_STUDENT", "Per student"
        TIERED = "TIERED", "Tiered (volume bands)"

    name = models.CharField(max_length=120, help_text="Plan name (e.g. Basic, Pro, Enterprise)")
    slug = models.SlugField(max_length=80, unique=True, help_text="Unique slug (e.g. basic, pro)")
    max_students = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max students on this plan; null = unlimited",
    )
    max_staff = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max staff on this plan; null = unlimited",
    )
    included_features = models.JSONField(
        default=list,
        blank=True,
        help_text="List of feature codes included (e.g. ['library', 'transport', 'design_studio'])",
    )
    billing_model = models.CharField(
        max_length=20,
        choices=BillingModel.choices,
        default=BillingModel.FLAT,
        blank=True,
    )
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed monthly price for FLAT model",
    )
    price_per_student = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Per-student monthly price for PER_STUDENT model",
    )
    tier_rules = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tier bands for TIERED model, e.g. [{\"max\": 500, \"price\": 200}, {\"max\": 2000, \"price\": 600}]",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Plan"
        verbose_name_plural = "Plans"

    def __str__(self):
        return self.name


# ============================================================================
# Global Powerhouse Phase G: Offline & low-bandwidth – Sync conflict tracking
# ============================================================================


class SyncConflict(models.Model):
    """
    Records a sync conflict when client's base_timestamp is older than server's
    updated_at. Surface in Sync Center for side-by-side resolution (keep server,
    keep client, or manual merge). Do not overwrite server data on conflict.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RESOLVED_SERVER = "RESOLVED_SERVER", "Kept server version"
        RESOLVED_CLIENT = "RESOLVED_CLIENT", "Kept client version"
        RESOLVED_MERGE = "RESOLVED_MERGE", "Merged manually"
        DISCARDED = "DISCARDED", "Discarded"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="sync_conflicts",
    )
    entity_type = models.CharField(max_length=40, help_text="e.g. student, attendance, classroom")
    entity_id = models.BigIntegerField(help_text="Primary key of the conflicted record")
    client_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Client/offline version of changed fields",
    )
    server_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Current server version of the record (relevant fields)",
    )
    client_updated_at = models.DateTimeField(null=True, blank=True)
    server_updated_at = models.DateTimeField(null=True, blank=True)
    reported_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_sync_conflicts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_sync_conflicts",
    )
    resolution_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sync conflict"
        verbose_name_plural = "Sync conflicts"
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} ({self.get_status_display()})"


# ============================================================================
# Global Powerhouse Phase E: Monetization — addons catalog, PPP, revenue, waivers
# ============================================================================


class PlanAddon(models.Model):
    """
    Add-on feature with price for Plan Configurator.
    GET plans, addons, country_multiplier — same contract for onboarding and PlanConfigurator.
    """
    code = models.SlugField(max_length=80, unique=True, help_text="Feature code e.g. design_studio")
    name = models.CharField(max_length=120, help_text="Display name")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Monthly price in base currency (before PPP multiplier)",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Plan add-on"
        verbose_name_plural = "Plan add-ons"

    def __str__(self):
        return f"{self.name} ({self.code})"


class CountryMultiplier(models.Model):
    """
    Regional PPP (purchasing power parity) multiplier for Plan Configurator (195-country).
    Final price = base * country_multiplier. Zone A/B/C for display (e.g. Zone A = premium, C = discounted).
    """
    class Zone(models.TextChoices):
        A = "A", "Zone A (premium)"
        B = "B", "Zone B (standard)"
        C = "C", "Zone C (discounted)"

    country_code = models.CharField(max_length=3, unique=True, help_text="ISO 3166-1 alpha-2/3")
    zone = models.CharField(
        max_length=1,
        choices=Zone.choices,
        blank=True,
        help_text="PPP zone for display (A/B/C).",
    )
    multiplier = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=1,
        help_text="Price multiplier (e.g. 0.6 for discounted region, 1.0 for base)",
    )
    name = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_code"]
        verbose_name = "Country price multiplier"
        verbose_name_plural = "Country price multipliers"

    def __str__(self):
        return f"{self.country_code}: {self.multiplier}"


# AI models moved to .models_ai for Phase 10 — 2.1 giant-file decomposition. Re-export for backward compatibility.
from .models_ai import (
    AIGatewayMetric,
    AIEmbeddingStore,
    AIModelRegistry,
    AIPromptClass,
    AIPromptRegistry,
    RegionalAIConfig,
)


class RevenueSnapshot(models.Model):
    """
    Monthly revenue snapshot per tenant for Financial Mission Control.
    calculate_monthly_stats fills this; dashboard shows total_mrr, total_waived, waiver_%.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="revenue_snapshots",
    )
    snapshot_date = models.DateField(help_text="First day of the month for this snapshot")
    actual_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Actual revenue from this tenant for the period",
    )
    waived_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Potential revenue waived (e.g. COMPLIMENTARY schools)",
    )
    billing_model = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=3, blank=True)
    student_count = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-snapshot_date", "school"]
        unique_together = [("school", "snapshot_date")]
        verbose_name = "Revenue snapshot"
        verbose_name_plural = "Revenue snapshots"

    def __str__(self):
        return f"{self.school.name} {self.snapshot_date}: {self.actual_revenue}"


class BillingWaiverAuditLog(models.Model):
    """
    Audit trail for billing_type and waiver_note changes (Phase E checklist).
    Who changed what and when for compliance and support.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="billing_waiver_audit_logs",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_waiver_changes",
    )
    old_billing_type = models.CharField(max_length=20, blank=True)
    new_billing_type = models.CharField(max_length=20)
    old_waiver_note = models.CharField(max_length=500, blank=True)
    new_waiver_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Billing waiver audit log"
        verbose_name_plural = "Billing waiver audit logs"

    def __str__(self):
        return f"{self.school.name} → {self.new_billing_type} at {self.created_at}"


class WaiverRequest(models.Model):
    """
    Request Waiver flow: school submits proof; SuperUser approves or denies.
    On approval: set school.billing_type = COMPLIMENTARY, waiver_note from request.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        DENIED = "DENIED", "Denied"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="waiver_requests",
    )
    proof_file = models.FileField(
        upload_to=tenant_upload_to_waiver_requests,
        blank=True,
        help_text="Proof of NGO / non-profit status",
    )
    reason = models.TextField(blank=True, help_text="Reason for waiver request")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="waiver_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Waiver request"
        verbose_name_plural = "Waiver requests"

    def __str__(self):
        return f"{self.school.name} — {self.status}"


# ============================================================================
# Section 7: Multi-Tenant Extensibility & Nuance Engine (JSON-Logic only)
# ============================================================================


class CustomNuance(models.Model):
    """
    Per-school logic injection: JSON-Logic only, no raw code.
    Gate by plan (nuance_engine / custom_logic add-on). Runner applies logic at hook_point.
    """
    HOOK_CHOICES = [
        ("tuition_calc", "Tuition / fee calculation"),
        ("grade_weight", "Grade weighting"),
        ("attendance_alert", "Attendance alerts"),
        ("fee_discount", "Fee discount eligibility"),
        ("generic", "Generic (custom)"),
    ]

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="custom_nuances",
    )
    hook_point = models.CharField(max_length=50, choices=HOOK_CHOICES)
    logic_data = models.JSONField(
        default=dict,
        help_text="JSON-Logic structure (e.g. {\"and\": [{\">\": [{\"var\": \"gpa\"}, 3.8]}, {\"var\": \"sibling_count\"}]}). Only allowed ops run.",
    )
    human_description = models.TextField(
        blank=True,
        help_text="Plain-language description (e.g. for Principal); can be AI-generated.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "hook_point"]
        unique_together = [("school", "hook_point")]
        verbose_name = "Custom nuance"
        verbose_name_plural = "Custom nuances"

    def __str__(self):
        return f"{self.school.name} — {self.get_hook_point_display()}"


class PendingNuance(models.Model):
    """
    Human-in-the-loop: proposed nuance (e.g. AI-generated) before it becomes active.
    Admin approves → promote to CustomNuance; reject → discard.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="pending_nuances",
    )
    hook_point = models.CharField(max_length=50, choices=CustomNuance.HOOK_CHOICES)
    proposed_logic = models.JSONField(default=dict, help_text="JSON-Logic to apply at hook_point")
    human_explanation = models.TextField(blank=True, help_text="Plain-language description for reviewer")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_nuances",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pending nuance"
        verbose_name_plural = "Pending nuances"

    def __str__(self):
        return f"{self.school.name} — {self.hook_point} ({self.status})"


# ============================================================================
# Section 8: Industry Interoperability — zero-hardcoding gateway
# ============================================================================


class ServiceIntegration(models.Model):
    """
    Per-school external tool config (LTI, OAuth, webhooks). DB-driven; never hardcode URLs.
    Section 8.3: client_id, client_secret (store encrypted in production), endpoint_url, enabled_scopes.
    Use for LTI 1.3 (deployment_id, public_key in config or extra fields), Google/M365, Clever, etc.
    """
    class ServiceType(models.TextChoices):
        LTI = "LTI", "LTI 1.3"
        OAUTH = "OAUTH", "OAuth 2.0 / OpenID"
        WEBHOOK = "WEBHOOK", "Webhook outbound"
        WHATSAPP = "WHATSAPP", "WhatsApp Business API"
        PUSH = "PUSH", "Push Notifications"
        STRIPE = "STRIPE", "Stripe"
        BADGES = "BADGES", "Digital Badges / Open Badges"
        OTHER = "OTHER", "Other"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="service_integrations",
    )
    service_name = models.CharField(max_length=100, help_text="e.g. Moodle, Stripe, Google Classroom")
    service_type = models.CharField(max_length=20, choices=ServiceType.choices, default=ServiceType.OTHER)
    client_id = models.CharField(max_length=255, blank=True)
    client_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text="Encrypt at rest in production; use for OAuth/LTI.",
    )
    endpoint_url = models.URLField(blank=True, help_text="Base URL for API or launch endpoint")
    enabled_scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g. ['grades.read', 'roster.write']. Strict scoping per module.",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="LTI: deployment_id, public_key; OAuth: redirect_uri, etc.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "service_name"]
        unique_together = [("school", "service_name")]
        verbose_name = "Service integration"
        verbose_name_plural = "Service integrations"

    def __str__(self):
        return f"{self.school.name} — {self.service_name}"


class WebhookSubscription(models.Model):
    """
    Section 8.3: External tools subscribe to events (exam.completed, fee.paid).
    Outbound payloads signed with HMAC; envelope: event_id, tenant_id, data.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="webhook_subscriptions",
    )
    event_type = models.CharField(max_length=80, help_text="e.g. exam.completed, fee.paid")
    target_url = models.URLField(help_text="Endpoint to POST the payload")
    secret = models.CharField(
        max_length=255,
        blank=True,
        help_text="HMAC secret for signing payloads",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "event_type"]
        verbose_name = "Webhook subscription"
        verbose_name_plural = "Webhook subscriptions"

    def __str__(self):
        return f"{self.school.name} — {self.event_type} → {self.target_url}"


class WebhookDelivery(models.Model):
    """
    Delivery ledger for outbound webhook events with retry and dead-letter support.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RETRYING = "RETRYING", "Retrying"
        DELIVERED = "DELIVERED", "Delivered"
        DEAD_LETTER = "DEAD_LETTER", "Dead letter"

    subscription = models.ForeignKey(
        "siteconfig.WebhookSubscription",
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=80)
    payload = models.JSONField(default=dict, blank=True)
    signature = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=4)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_attempt_at", "created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="siteconfig_webhook_queue_idx"),
            models.Index(fields=["event_type", "created_at"], name="siteconfig_webhook_event_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "event_id"],
                name="siteconfig_unique_subscription_event_delivery",
            )
        ]

    def __str__(self):
        return f"{self.subscription_id}:{self.event_type}:{self.event_id} [{self.status}]"


# ============================================================================
# Request-to-Feature & Feature Fragment (plan 3.20, 3.26)
# ============================================================================


class CustomFeatureTicket(models.Model):
    """
    School-submitted custom requirement; SuperAdmin (or AI) creates FeatureFragment.
    Workflow: Submitted → In Review → Approved / Rejected.
    """
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        IN_REVIEW = "IN_REVIEW", "In Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="custom_feature_tickets",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    reviewer_comment = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_feature_tickets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Vision Board: upvotes (195-country / multi-tenant); VIP = high-priority for roadmap.
    upvote_count = models.PositiveIntegerField(default=0, help_text="Upvotes from school admins (Vision Board).")
    is_vip = models.BooleanField(default=False, help_text="VIP / high-priority feature request for roadmap.")

    class Meta:
        ordering = ["-is_vip", "-upvote_count", "-created_at"]
        indexes = [models.Index(fields=["school", "status"]), models.Index(fields=["is_vip", "-upvote_count"])]

    def __str__(self):
        return f"{self.school.name}: {self.title} ({self.status})"


def get_feature_fragment_cap(school) -> int | None:
    """Plan cap for FeatureFragment (plan 3.26): Basic 0, Pro 2, Enterprise 5. None = unlimited."""
    if not school:
        return 0
    plan = getattr(school, "plan", None)
    if not plan:
        return 0
    slug = (getattr(plan, "slug", None) or "").strip().lower()
    caps = {"basic": 0, "pro": 2, "enterprise": 5}
    return caps.get(slug, 0)


class FeatureFragment(models.Model):
    """
    Custom UI/logic fragment for a school: target_hook (e.g. STUDENT_PROFILE_SIDEBAR),
    metadata_schema (JSONB). Plan cap: Basic 0, Pro 2, Enterprise 5.
    schema_version for backward compatibility when metadata evolves.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feature_fragments",
    )
    name = models.CharField(max_length=120)
    target_hook = models.CharField(
        max_length=80,
        help_text="e.g. STUDENT_PROFILE_SIDEBAR, GRADEBOOK_SIDEBAR",
    )
    metadata_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Config and optional HTML/snippet for the hook",
    )
    schema_version = models.PositiveSmallIntegerField(
        default=1,
        help_text="Increment when metadata_schema format changes",
    )
    ticket = models.ForeignKey(
        CustomFeatureTicket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fragments",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "target_hook"]
        unique_together = [("school", "target_hook")]
        indexes = [models.Index(fields=["school", "is_active"])]

    def __str__(self):
        return f"{self.school.name}: {self.target_hook}"

    def clean(self):
        from django.core.exceptions import ValidationError
        cap = get_feature_fragment_cap(self.school)
        if cap is not None:
            qs = FeatureFragment.objects.filter(school=self.school)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.count() >= cap:
                raise ValidationError(
                    {"__all__": [f"Plan limit reached: this school can have at most {cap} custom fragment(s). Upgrade to add more."]}
                )
        super().clean()


# ============================================================================
# Global Powerhouse Phase F: Design Studio & branding
# ============================================================================


class DesignTemplate(models.Model):
    """
    Design Studio: JSON layout blueprint for report cards, certificates, etc.
    One document type first (e.g. certificate or report_card); hydrate with data and render to PDF (WeasyPrint).
    """
    class DocumentType(models.TextChoices):
        REPORT_CARD = "report_card", "Report card"
        CERTIFICATE = "certificate", "Certificate"
        INVOICE = "invoice", "Invoice"
        ID_CARD = "id_card", "ID card"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="design_templates",
    )
    name = models.CharField(max_length=120, help_text="Template name")
    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
        default=DocumentType.CERTIFICATE,
    )
    layout = models.JSONField(
        default=dict,
        blank=True,
        help_text="Layout blueprint: widgets, positions, placeholders e.g. {{student_name}}",
    )
    is_default = models.BooleanField(default=False, help_text="Use as default for this document type")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "document_type", "name"]
        unique_together = [("school", "document_type", "name")]
        verbose_name = "Design template"
        verbose_name_plural = "Design templates"

    def __str__(self):
        return f"{self.school.name}: {self.get_document_type_display()} — {self.name}"

class BrandProfile(models.Model):
    """
    Canonical tenant brand hub. All runtime tenant branding should resolve through this model.
    Legacy BrandSettings and School branding fields remain migration inputs and compatibility fallbacks.
    """
    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="brand_profile",
    )
    logo_url = models.URLField(blank=True, help_text="Primary tenant logo URL.")
    logo_dark_url = models.URLField(blank=True, help_text="Optional dark-surface logo URL.")
    favicon_url = models.URLField(blank=True, help_text="Optional tenant favicon URL.")
    tagline = models.CharField(max_length=255, blank=True)
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    secondary_color = models.CharField(max_length=20, blank=True, default="")
    accent_color = models.CharField(max_length=20, default="#198754")
    font_family = models.CharField(max_length=160, blank=True)
    login_background_url = models.URLField(blank=True)
    portal_visual = models.CharField(max_length=120, blank=True)
    email_template = models.CharField(max_length=120, blank=True)
    pdf_template = models.CharField(max_length=120, blank=True)
    certificate_template = models.CharField(max_length=120, blank=True)
    tokens = models.JSONField(
        default=dict,
        blank=True,
        help_text="Theme tokens used across login, portal, reports, and emails.",
    )
    templates = models.JSONField(
        default=dict,
        blank=True,
        help_text="Template and layout bindings for branded surfaces.",
    )
    assets = models.JSONField(
        default=dict,
        blank=True,
        help_text="Versioned asset references and brand media metadata.",
    )
    custom_css = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand profile"
        verbose_name_plural = "Brand profiles"

    def __str__(self):
        return f"Brand profile: {self.school.name}"


class BrandSettings(models.Model):
    """
    Phase F (optional): Explicit branding per tenant (logo, colors, custom_css).
    When present, use instead of School.logo_url, primary_color, accent_color for white-label.
    """
    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="brand_settings",
    )
    logo_url = models.URLField(blank=True, help_text="URL to tenant logo")
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    custom_css = models.TextField(blank=True, help_text="Optional custom CSS for tenant")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand settings"
        verbose_name_plural = "Brand settings"

    def __str__(self):
        return f"Brand: {self.school.name}"


class GradingScaleConfig(models.Model):
    """
    Define grading scales per region.
    Allows conversion between different evaluation systems.
    """
    region = models.ForeignKey(
        RegionConfig, 
        on_delete=models.CASCADE, 
        related_name='grading_scales',
        related_query_name='gradingscaleconfig',
        help_text="Region this scale applies to"
    )
    scale_type = models.CharField(
        max_length=20,
        help_text="Scale identifier (0-20, 0-100, 0-10, a-f, gpa)"
    )
    
    # Scale range
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Display format
    display_format = models.CharField(
        max_length=50,
        help_text="Format string for display (e.g., '{score:.0f}/20', '{score:.1f}%')"
    )
    
    # Grade breakpoints (0-20 scale)
    grade_a_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_b_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_c_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_d_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_f_min = models.DecimalField(max_digits=5, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('region', 'scale_type')
        ordering = ['region', 'scale_type']
    
    def __str__(self):
        return f"{self.region.name} - {self.scale_type}"
    
    def get_letter_grade(self, score):
        """Convert numerical score to letter grade (A-F)."""
        score = Decimal(str(score))
        if score >= self.grade_a_min:
            return 'A'
        elif score >= self.grade_b_min:
            return 'B'
        elif score >= self.grade_c_min:
            return 'C'
        elif score >= self.grade_d_min:
            return 'D'
        else:
            return 'F'


from apps.academics.models import HolidayCalendar  # noqa: E402,F401

class WeatherLocation(models.Model):
    """
    Configurable weather locations for the header/context strip.
    Lets operators choose country -> city without hardcoding coordinates in templates.
    """

    region = models.ForeignKey(
        RegionConfig,
        on_delete=models.CASCADE,
        related_name="weather_locations",
    )
    city = models.CharField(max_length=120)
    label = models.CharField(max_length=180, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    timezone = models.CharField(max_length=64, default="UTC")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["region__name", "sort_order", "city"]
        unique_together = [("region", "city")]

    def __str__(self):
        return self.display_label

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label
        return f"{self.city}, {self.region.name}"

    def to_weather_flags(self) -> dict:
        return {
            "header_weather_country_code": self.region_id,
            "header_weather_city": self.city,
            "header_weather_label": self.display_label,
            "header_weather_latitude": self.latitude,
            "header_weather_longitude": self.longitude,
            "header_weather_timezone": self.timezone or self.region.timezone or "UTC",
        }

    @classmethod
    def _seed_rows(cls) -> list[dict]:
        return [
            {
                "country_code": "GLOBAL",
                "country_name": "Global Default",
                "city": "UTC",
                "label": "Global Default (UTC)",
                "latitude": 0.0,
                "longitude": 0.0,
                "timezone": "UTC",
                "sort_order": 0,
            },
            {
                "country_code": "CMR",
                "country_name": "Cameroon",
                "city": "Buea",
                "label": "Buea, Cameroon",
                "latitude": 4.1527,
                "longitude": 9.2410,
                "timezone": "Africa/Douala",
                "sort_order": 10,
            },
            {
                "country_code": "CMR",
                "country_name": "Cameroon",
                "city": "Douala",
                "label": "Douala, Cameroon",
                "latitude": 4.0511,
                "longitude": 9.7679,
                "timezone": "Africa/Douala",
                "sort_order": 20,
            },
            {
                "country_code": "USA",
                "country_name": "United States",
                "city": "New York",
                "label": "New York, United States",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timezone": "America/New_York",
                "sort_order": 10,
            },
            {
                "country_code": "USA",
                "country_name": "United States",
                "city": "Los Angeles",
                "label": "Los Angeles, United States",
                "latitude": 34.0522,
                "longitude": -118.2437,
                "timezone": "America/Los_Angeles",
                "sort_order": 20,
            },
            {
                "country_code": "GBR",
                "country_name": "United Kingdom",
                "city": "London",
                "label": "London, United Kingdom",
                "latitude": 51.5072,
                "longitude": -0.1276,
                "timezone": "Europe/London",
                "sort_order": 10,
            },
            {
                "country_code": "NGA",
                "country_name": "Nigeria",
                "city": "Lagos",
                "label": "Lagos, Nigeria",
                "latitude": 6.5244,
                "longitude": 3.3792,
                "timezone": "Africa/Lagos",
                "sort_order": 10,
            },
            {
                "country_code": "KEN",
                "country_name": "Kenya",
                "city": "Nairobi",
                "label": "Nairobi, Kenya",
                "latitude": -1.2864,
                "longitude": 36.8172,
                "timezone": "Africa/Nairobi",
                "sort_order": 10,
            },
            {
                "country_code": "FRA",
                "country_name": "France",
                "city": "Paris",
                "label": "Paris, France",
                "latitude": 48.8566,
                "longitude": 2.3522,
                "timezone": "Europe/Paris",
                "sort_order": 10,
            },
        ]

    @classmethod
    def ensure_seed_data(cls) -> None:
        if cls.objects.exists():
            return
        for row in cls._seed_rows():
            country_defaults = GlobalGeoCatalog.country_defaults(row["country_code"])
            region, _ = RegionConfig.objects.get_or_create(
                code=row["country_code"],
                defaults={
                    "name": row["country_name"],
                    "default_language": country_defaults.get("default_language") or "en",
                    "timezone": row["timezone"] or country_defaults.get("timezone") or "UTC",
                    "date_format": "YYYY-MM-DD" if row["country_code"] == "GLOBAL" else "DD/MM/YYYY",
                    "grading_scale": "0-100",
                    "default_currency": country_defaults.get("currency") or "USD",
                    "academic_year_start_month": 9,
                    "term_count_per_year": 3,
                },
            )
            cls.objects.get_or_create(
                region=region,
                city=row["city"],
                defaults={
                    "label": row["label"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "timezone": row["timezone"],
                    "sort_order": row["sort_order"],
                },
            )

    @classmethod
    def get_default(cls):
        cls.ensure_seed_data()
        preferred_timezone = getattr(settings, "TIME_ZONE", "UTC") or "UTC"
        location = (
            cls.objects.select_related("region")
            .filter(is_active=True, timezone=preferred_timezone)
            .order_by("sort_order", "city")
            .first()
        )
        if location:
            return location
        return cls.objects.select_related("region").filter(is_active=True).order_by("sort_order", "city").first()


class FeatureToggleDefinition(models.Model):
    """
    Registry of configurable toggles.
    Supports global defaults plus optional per-school overrides.
    """

    class Scope(models.TextChoices):
        GLOBAL = "global", "Global only"
        SCHOOL = "school", "School override allowed"

    key = models.SlugField(max_length=120, unique=True)
    label = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.SCHOOL)
    default_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "label", "key"]

    def __str__(self):
        return self.label or self.key


class FeatureToggleState(models.Model):
    """
    Effective toggle values.
    - school=None => global override
    - school=<id> => tenant override
    """

    definition = models.ForeignKey(
        FeatureToggleDefinition,
        on_delete=models.CASCADE,
        related_name="states",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feature_toggle_states",
        null=True,
        blank=True,
    )
    is_enabled = models.BooleanField(default=False)
    value = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, this override is ignored after this time (Phase 10 — 10.2 capability expiry).",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_feature_toggle_states",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "school"],
                name="siteconfig_toggle_state_unique_definition_school",
            )
        ]
        ordering = ["definition__key", "school_id"]

    def __str__(self):
        scope = self.school.slug if self.school_id else "global"
        return f"{self.definition.key} ({scope})"

def _refresh_site_settings_cache(sender, instance: SiteSettings, **kwargs) -> None:
    global _SITE_SETTINGS_CACHE
    _SITE_SETTINGS_CACHE = instance


def _emit_global_change_alert(sender, instance: SiteSettings, **kwargs) -> None:
    """
    Optional (plan 4.6): Notify security/ops when SiteSettings changes.
    Set GLOBAL_CHANGE_ALERT_WEBHOOK_URL to a URL (e.g. Slack incoming webhook);
    this handler POSTs a JSON summary (no secrets) in a background thread.
    """
    import os
    import threading
    url = os.environ.get("GLOBAL_CHANGE_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return
    payload = {
        "event": "site_settings_changed",
        "id": instance.pk,
        "changed_at": instance.updated_at.isoformat() if getattr(instance, "updated_at", None) else None,
    }
    def _post():
        try:
            import urllib.request
            import urllib.error
            import json
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except (OSError, TimeoutError, TypeError, ValueError, urllib.error.URLError):
            logger = logging.getLogger(__name__)
            logger.warning("Global change alert webhook failed", exc_info=True)
    t = threading.Thread(target=_post, daemon=True)
    t.start()


def _clear_site_settings_cache(sender, **kwargs) -> None:
    global _SITE_SETTINGS_CACHE
    _SITE_SETTINGS_CACHE = None


# Plan XVI: Onboarding tours and feature-usage analytics
class TourStep(models.Model):
    """In-app onboarding tour step; track which users have seen which step."""
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="tour_steps",
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=80, db_index=True, help_text="e.g. dashboard_welcome, grades_first_time")
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        unique_together = [("school", "code")]

    def __str__(self):
        return f"{self.code}: {self.title or self.code}"


class FeatureUsageEvent(models.Model):
    """Feature-usage analytics: track_event(feature_code, school, user)."""
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feature_usage_events",
        null=True,
        blank=True,
    )
    feature_code = models.CharField(max_length=80, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feature_usage_events",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "feature_code", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.feature_code} @ {self.created_at}"


# ============================================================================
# Global Support Desk (RunMyCampus powerhouse): central ticketing in shared schema
# ============================================================================


class GlobalSupportTicket(models.Model):
    """
    Central support ticket from any tenant; stored in public/shared schema.
    Super-admin command center can filter by tenant, priority, region (metadata.country_code).
    Auto-prioritize by plan (e.g. Powerhouse).
    """
    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        WAITING = "WAITING", "Waiting"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="global_support_tickets",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="global_support_tickets_submitted",
    )
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
        help_text="Super-admin or support agent assigned to this ticket.",
    )
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="country_code, plan_slug, etc. for regional routing and filters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    first_response_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the first agent response was recorded; used for SLA response breach.",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["school"]),
            models.Index(fields=["-created_at"]),
        ]
        verbose_name = "Global support ticket"
        verbose_name_plural = "Global support tickets"

    def __str__(self):
        return f"{self.school.name}: {self.subject} ({self.status})"


# ============================================================================
# Regional marketing pitch (geo-personalized landing); shared schema
# ============================================================================


class RegionalPitch(models.Model):
    """
    Per-country (or region) marketing copy and SEO for the public landing.
    Loaded by GeoIP or tenant region; morphs headline, features, and SEO metadata.
    """
    country_code = models.CharField(
        max_length=2,
        unique=True,
        db_index=True,
        help_text="ISO 3166-1 alpha-2 (e.g. CM, CA).",
    )
    headline = models.CharField(max_length=200)
    subheadline = models.CharField(max_length=400, blank=True)
    features = models.JSONField(
        default=list,
        blank=True,
        help_text="List of feature strings or {title, description} dicts.",
    )
    visual_variant = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional: hero image or layout variant key.",
    )
    seo_title = models.CharField(max_length=120, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_code"]
        verbose_name = "Regional pitch"
        verbose_name_plural = "Regional pitches"

    def __str__(self):
        return f"{self.country_code}: {self.headline}"


# ============================================================================
# Global Brand Registry (country-level source of truth for SEO/UI/labels)
# ============================================================================


class GlobalBrandRegistry(models.Model):
    """
    Canonical per-country brand and academic defaults used for:
    - marketing SEO hydration
    - tenant terminology/localization hydration
    - compliance and UI behavior defaults
    """

    iso_code = models.CharField(
        max_length=2,
        primary_key=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g. CM, CA, BR).",
    )
    country_name = models.CharField(max_length=120)
    primary_language = models.CharField(
        max_length=16,
        default="en",
        help_text="Primary language code for this country profile (e.g. en, fr, ar).",
    )
    academic_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="ISCED levels, term structure, grading defaults, and education nuances.",
    )
    labels_map = models.JSONField(
        default=dict,
        blank=True,
        help_text="Terminology map (student, teacher, principal, etc.) for UI hydration.",
    )
    compliance_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Data residency and privacy-law defaults for this country.",
    )
    seo_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Marketing SEO defaults (headlines, summaries, proof points, metadata).",
    )
    ui_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="UI defaults such as date format, number separators, RTL, and locale hints.",
    )
    currency_code = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)
    source_name = models.CharField(
        max_length=64,
        blank=True,
        default="global_catalog",
        help_text="Data source name (e.g. global_catalog, unesco_uis, manual).",
    )
    source_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["iso_code"]
        verbose_name = "Global brand registry"
        verbose_name_plural = "Global brand registry"

    def __str__(self):
        return f"{self.iso_code} - {self.country_name}"


# ============================================================================
# Impersonation audit (super-admin "view as tenant"); stored in shared schema
# ============================================================================


class ImpersonationLog(models.Model):
    """Audit log for super-admin tenant impersonation (switch-to-tenant / end)."""

    class Action(models.TextChoices):
        SWITCH = "SWITCH", "Switch to tenant"
        END = "END", "End impersonation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="impersonation_logs",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="impersonation_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["actor"]), models.Index(fields=["school"]), models.Index(fields=["-created_at"])]
        verbose_name = "Impersonation log"
        verbose_name_plural = "Impersonation logs"

    def __str__(self):
        return f"{self.actor_id} {self.action} {self.school_id} @ {self.created_at}"


class GlobalSyllabus(models.Model):
    """
    World Engine: global syllabus/standards nodes for semantic mapping (scanned syllabi → suggest/map to nodes).
    Used with Ollama/embeddings for syllabus tagging and national syllabus sync.
    """
    code = models.CharField(max_length=120, unique=True, help_text="Unique code (e.g. subject-grade-topic).")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    country_code = models.CharField(max_length=10, blank=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["country_code", "sort_order", "code"]
        verbose_name = "Global syllabus node"
        verbose_name_plural = "Global syllabus nodes"

    def __str__(self):
        return f"{self.code}: {self.name}"


class LearningPassport(models.Model):
    """
    World Engine: learner credential / record (195-country; UNICEF-style).
    Links learner (user/school) to achievements and optionally to GlobalSyllabus nodes.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_passports",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="learning_passports",
    )
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    credentials = models.JSONField(default=dict, blank=True, help_text="Achievements, badges, mapped syllabus nodes.")
    country_code = models.CharField(max_length=10, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [("user", "school")]
        verbose_name = "Learning passport"
        verbose_name_plural = "Learning passports"

    def __str__(self):
        return f"Passport {self.user_id} ({self.school_id or 'global'})"


class BreakGlassOverride(models.Model):
    """
    World Engine: break-glass protocol — emergency override (e.g. unlock, bypass) with audit.
    Scope = e.g. 'lockdown_unlock', 'impersonation_bypass'; actor = who invoked; reason required.
    """
    scope = models.CharField(max_length=80, db_index=True)
    target_id = models.CharField(max_length=255, blank=True, help_text="e.g. user_id, school_id.")
    reason = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["scope", "target_id"])]

    def __str__(self):
        return f"{self.scope} by {self.actor_id} @ {self.created_at}"


class BroadcastCampaign(models.Model):
    """
    World Engine: Emergency Broadcast — message to 5k+ devices; WebSocket/Redis Pub/Sub; optional Slide to Confirm.
    Celery task fans out in chunks; delivery tracked per recipient.
    """
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUEUED = "QUEUED", "Queued"
        SENDING = "SENDING", "Sending"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="broadcast_campaigns",
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    slide_confirm_required = models.BooleanField(default=True, help_text="Recipient must slide-to-confirm.")
    target_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} ({self.status})"


class ProductFeedback(models.Model):
    """
    Part 4.4: Public-schema feedback/feature requests for roadmap visibility.
    Tag by region and module; status (Planned / In Development / Released); optional upvotes.
    Link from roadmap or feedback form; simple admin for super-admin.
    """
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        PLANNED = "PLANNED", "Planned"
        IN_DEVELOPMENT = "IN_DEVELOPMENT", "In Development"
        RELEASED = "RELEASED", "Released"
        WONT_DO = "WONT_DO", "Won't Do"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    region = models.CharField(max_length=32, blank=True, db_index=True, help_text="e.g. country code or regional cluster.")
    module = models.CharField(max_length=64, blank=True, db_index=True, help_text="e.g. admissions, finance, portal.")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    upvotes = models.PositiveIntegerField(default=0)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_productfeedback"
        ordering = ["-upvotes", "-created_at"]
        verbose_name = "Product feedback"
        verbose_name_plural = "Product feedback"

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class MarketingContent(models.Model):
    """
    Plan 4.11: DB-driven content for marketing (CMS-lite). Key-based blobs editable in admin
    without deploy. Use for hero copy, footer, or any marketing snippet; locale optional.
    """
    key = models.CharField(max_length=120, db_index=True, help_text="e.g. hero_subheadline, blog_intro")
    content_html = models.TextField(blank=True)
    locale = models.CharField(max_length=10, blank=True, default="", db_index=True)
    content_type = models.CharField(max_length=32, blank=True, default="html")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_marketingcontent"
        unique_together = [["key", "locale"]]
        ordering = ["key", "locale"]
        verbose_name = "Marketing content"
        verbose_name_plural = "Marketing content"

    def __str__(self):
        return f"{self.key} ({self.locale or 'default'})"


class BlogPost(models.Model):
    """
    Plan 4.11: Blog / News for marketing site. CMS-backed; list on /blog/, detail at /blog/<slug>/.
    """
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    excerpt = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_blogpost"
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Blog post"
        verbose_name_plural = "Blog posts"

    def __str__(self):
        return self.title


# Section 15.2: Metadata-driven data layer — custom attributes without code/schema migrations
class DynamicFieldDefinition(models.Model):
    """Defines a custom field for an entity type (e.g. Student, Invoice). No DB schema change per field."""
    class DataType(models.TextChoices):
        TEXT = "TEXT", "Text"
        NUMBER = "NUMBER", "Number"
        DATE = "DATE", "Date"
        BOOLEAN = "BOOLEAN", "Boolean"
        JSON = "JSON", "JSON"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="dynamic_field_definitions")
    entity_type = models.CharField(max_length=64, db_index=True)  # e.g. "StudentProfile", "Invoice"
    field_key = models.CharField(max_length=128, db_index=True)
    label = models.CharField(max_length=255)
    data_type = models.CharField(max_length=16, choices=DataType.choices, default=DataType.TEXT)
    required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["school", "entity_type", "field_key"]]
        ordering = ["entity_type", "field_key"]

    def __str__(self):
        return f"{self.entity_type}.{self.field_key}"


class DynamicFieldValue(models.Model):
    """Stores a value for a custom field on a specific entity instance."""
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="dynamic_field_values")
    entity_type = models.CharField(max_length=64, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)  # PK of the entity
    field_key = models.CharField(max_length=128, db_index=True)
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_json = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [["school", "entity_type", "object_id", "field_key"]]
        indexes = [models.Index(fields=["school", "entity_type", "object_id"])]

    def __str__(self):
        return f"{self.entity_type}#{self.object_id}.{self.field_key}"


post_save.connect(_refresh_site_settings_cache, sender=SiteSettings)
post_save.connect(_emit_global_change_alert, sender=SiteSettings)
post_delete.connect(_clear_site_settings_cache, sender=SiteSettings)

