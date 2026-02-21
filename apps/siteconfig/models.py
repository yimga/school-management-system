from __future__ import annotations

from decimal import Decimal
import logging

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
from apps.reports.models import ReportCard

logger = logging.getLogger(__name__)

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
        "header_weather_country_code": "CMR",
        "header_weather_city": "Buea",
        "header_weather_label": "Buea, Cameroon",
        "header_weather_latitude": 4.1527,
        "header_weather_longitude": 9.2410,
        "header_weather_timezone": "Africa/Douala",
        "header_weather_temperature_unit": "celsius",
    }


def default_backend_feature_flags():
    weather = default_header_weather_config()
    return {
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
        "show_header_context_weather": True,
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
        "enable_ministry_api_cartescolaire": False,
        "enable_ministry_api_dgi": False,
        "enable_ministry_live_sync": False,
        "enable_analytics_dashboard_cache": False,
        "enable_super_admin_ui": True,
        "marksheet_ocr_enabled": False,
        "marksheet_ocr_mobile_upload_enabled": True,
        "enable_api_center": False,
        "announcement_allow_submit_for_approval": False,
        "announcement_submit_for_approval_roles": ["TEACHER", "COMMS_STAFF"],
    }


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
        site = SiteSettings.get_solo()
        per_role = getattr(site, "default_widgets_per_role", None) or {}
        if isinstance(per_role, dict) and role_key in per_role:
            role_list = per_role.get(role_key)
            if isinstance(role_list, list) and role_list:
                valid_ids = {key for key, _ in DASHBOARD_WIDGET_OPTIONS}
                filtered = [w for w in role_list if str(w).strip() in valid_ids]
                if filtered:
                    return filtered
    except Exception:
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
    site_name = models.CharField(max_length=120, default="Gilead School System")
    tagline = models.CharField(max_length=200, blank=True, default="Knowledge ƒ?› Technology ƒ?› Excellence")
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
        default="GIL",
        help_text="Short code used in admission numbers (e.g., GIL).",
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
        default="Ministry of Education - Cameroon | UNESCO Standards 2026 Compliant",
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
        default="Powered by Gilead Technical High School.",
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
    sms_sender_id = models.CharField(max_length=50, default='GILEAD')
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

    # Compliance profile (finance/payroll)
    compliance_profile = models.ForeignKey(
        "finance.ComplianceProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_settings",
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
                except Exception:
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
                    except Exception:
                        pass
                    pass

    @classmethod
    def get_solo(cls) -> "SiteSettings":
        global _SITE_SETTINGS_CACHE
        cls._ensure_preview_columns()
        if _SITE_SETTINGS_CACHE is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            _SITE_SETTINGS_CACHE = obj
        else:
            try:
                _SITE_SETTINGS_CACHE.refresh_from_db()
            except cls.DoesNotExist:
                obj, _ = cls.objects.get_or_create(pk=1)
                _SITE_SETTINGS_CACHE = obj
            except DatabaseError:
                return _SITE_SETTINGS_CACHE
        _SITE_SETTINGS_CACHE._sanitize_foreign_keys(persist=True)
        return _SITE_SETTINGS_CACHE

    def _sanitize_foreign_keys(self, *, persist: bool = False) -> list[str]:
        fk_guards = (
            ("theme_pack", "siteconfig", "ThemePack"),
            ("admin_theme_pack", "siteconfig", "ThemePack"),
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
        ("other", "Other"),
    ]

    CATEGORIES = [
        ("LMS", "LMS"),
        ("PAYMENT", "Payment"),
        ("ATTENDANCE", "Attendance"),
        ("LIBRARY", "Library"),
        ("AI", "AI"),
        ("SIS", "SIS"),
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"{self.user.username} preferences"


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
        if report_type == ReportCard.Type.TERM:
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


class ReportCardStyleAssignment(models.Model):
    classroom = models.OneToOneField(
        Classroom,
        on_delete=models.CASCADE,
        related_name="report_card_style_assignment",
    )
    style = models.ForeignKey(
        ReportCardStyle,
        on_delete=models.PROTECT,
        related_name="assignments",
    )

    class Meta:
        ordering = ["classroom__name"]

    def __str__(self):
        return f"{self.classroom} → {self.style.name}"


def get_report_card_style_for_student(student: StudentProfile, report_type: str) -> ReportCardStyle | None:
    if not student or not student.classroom:
        return None
    assignment = getattr(student.classroom, "report_card_style_assignment", None)
    if assignment and assignment.style and assignment.style.is_active:
        return assignment.style

    site = SiteSettings.get_solo()
    default_field = "default_term_report_style" if report_type == ReportCard.Type.TERM else "default_annual_report_style"
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
        choices=[(2, '2 terms'), (3, '3 terms'), (4, '4 terms')]
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
        """Get default region (Cameroon), creating if necessary."""
        region, _ = cls.objects.get_or_create(
            code='CMR',
            defaults={
                'name': 'Cameroon',
                'default_language': 'en',
                'timezone': 'Africa/Douala',
                'date_format': 'DD/MM/YYYY',
                'grading_scale': '0-20',
                'default_currency': 'XAF',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            }
        )
        return region


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


class HolidayCalendar(models.Model):
    """
    Store holidays and important dates per region and academic year.
    Controls when school is closed and affects attendance tracking.
    """
    from apps.academics.models import AcademicYear
    
    HOLIDAY_TYPE_CHOICES = [
        ('school_holiday', 'School Holiday'),
        ('public_holiday', 'Public Holiday'),
        ('exam_period', 'Exam Period'),
        ('religious', 'Religious Holiday'),
        ('special_event', 'Special Event'),
    ]
    
    region = models.ForeignKey(
        RegionConfig, 
        on_delete=models.CASCADE, 
        related_name='holidays',
        help_text="Region this holiday applies to"
    )
    academic_year = models.ForeignKey(
        'academics.AcademicYear',
        on_delete=models.CASCADE, 
        related_name='holidays_by_region',
        help_text="Academic year for this holiday"
    )
    
    name = models.CharField(
        max_length=200,
        help_text="Holiday name (e.g., 'Christmas Break', 'Eid al-Fitr')"
    )
    date_start = models.DateField(help_text="Holiday start date")
    date_end = models.DateField(help_text="Holiday end date (inclusive)")
    
    holiday_type = models.CharField(
        max_length=50, 
        choices=HOLIDAY_TYPE_CHOICES,
        help_text="Type of holiday"
    )
    
    is_working_day = models.BooleanField(
        default=False,
        help_text="Some regions work during certain holidays (e.g., religious holidays)"
    )
    
    description = models.TextField(blank=True, help_text="Holiday description")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('region', 'academic_year', 'name')
        ordering = ['date_start']
    
    def __str__(self):
        return f"{self.region.code} - {self.name} ({self.date_start.year})"
    
    def overlaps_date(self, date):
        """Check if a specific date falls within this holiday."""
        return self.date_start <= date <= self.date_end


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
            region, _ = RegionConfig.objects.get_or_create(
                code=row["country_code"],
                defaults={
                    "name": row["country_name"],
                    "default_language": "en",
                    "timezone": row["timezone"],
                    "date_format": "DD/MM/YYYY",
                    "grading_scale": "0-100",
                    "default_currency": "USD",
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
        location = (
            cls.objects.select_related("region")
            .filter(region_id="CMR", city__iexact="Buea")
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


def _clear_site_settings_cache(sender, **kwargs) -> None:
    global _SITE_SETTINGS_CACHE
    _SITE_SETTINGS_CACHE = None


post_save.connect(_refresh_site_settings_cache, sender=SiteSettings)
post_delete.connect(_clear_site_settings_cache, sender=SiteSettings)
