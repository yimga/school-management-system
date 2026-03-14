from __future__ import annotations

from decimal import Decimal
import logging

from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import models, connection, OperationalError, DatabaseError
from django.db.models.fields.files import FieldFile
from django.db.models.signals import post_delete, post_save
from django.core.validators import MinValueValidator, MaxValueValidator
from .image_utils import optimize_image
from django.apps import apps as django_apps

from apps.academics.models import HolidayCalendar  # noqa: F401
from .domain_ownership import OWNERSHIP_DOMAINS, classify_site_settings_field

logger = logging.getLogger(__name__)

# Phase 2/7: Tenant behavior must not be sourced from SiteSettings; use runtime resolvers and
# bounded-context services. Migration plan: docs/SITECONFIG_OWNERSHIP_MIGRATION.md

REPORT_CARD_TYPE_TERM = "TERM"
REPORT_CARD_TYPE_ANNUAL = "ANNUAL"
PLATFORM_DEFAULT_SITE_NAME = "RunMyCampus"
PLATFORM_DEFAULT_SCHOOL_CODE = "RMC"
PLATFORM_DEFAULT_TAGLINE = "Education management for every school."
PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL = "support@runmycampus.com"
LEGACY_PLACEHOLDER_REPORT_DOMAINS = {"".join(["g", "ilead", "tech", ".", "edu"])}
LEGACY_PLACEHOLDER_SITE_NAMES = {"", "School System"}
LEGACY_PLACEHOLDER_SCHOOL_CODES = {"", "GIL"}
LEGACY_PLACEHOLDER_TAGLINES = {
    "",
    "Knowledge ƒ?› Technology ƒ?› Excellence",
    "Knowledge > Technology > Excellence",
}
LEGACY_PLACEHOLDER_REPORT_PHONES = {"", "+237 670 000 000"}


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


from .models_support import (  # noqa: F401
    default_admin_portal_stats_config,
    default_announcement_submit_for_approval_roles,
    default_backend_feature_flags,
    default_footer_badges,
    default_footer_links,
    default_portal_announcements,
    default_portal_features,
    default_portal_quick_actions,
    default_portal_recent_grades,
    default_portal_upcoming_assessments,
    default_social_links,
)  # noqa: F401


from .models_support import (  # noqa: F401
    DashboardView,
    ThemeLayout,
    PORTAL_FEATURE_DEFAULTS,
    PORTAL_FEATURE_OPTIONS,
    build_platform_default_site_settings,
    default_dashboard_widgets,
    default_header_weather_config,
    get_dashboard_widget_choices,
    resolve_dashboard_widgets,
    filter_portal_items,
    _normalized_report_preview_email,
    _normalized_report_preview_phone,
    _normalized_school_code,
    _normalized_site_name,
    _normalized_tagline,
    _payload_bool,
    _payload_decimal,
    _payload_float,
    _payload_int,
    _payload_int_list,
    _payload_json_object,
    _payload_string,
    _payload_string_list,
    _site_settings_json_safe,
    default_delegation_role_mapping,
    default_grade_approval_roles,
    default_grade_post_roles,
    default_syllabus_approval_roles,
    get_report_card_style_owner_model,
    get_theme_pack_owner_model,
)  # noqa: F401


_SITE_SETTINGS_CACHE: "SiteSettings | None" = None


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
    # Color harmony for theme palette (DETAILED_IMPLEMENTATION_PLAN / NON_NEGOTIABLE_BACKLOG item 7)
    THEME_HARMONY_CHOICES = [
        ("square", "Square (four evenly spaced hues)"),
        ("achromatic", "Achromatic (grayscale)"),
        ("polychromatic", "Polychromatic (multi-hue)"),
        ("diad", "Diad (two hues)"),
    ]
    theme_harmony = models.CharField(
        max_length=20,
        choices=THEME_HARMONY_CHOICES,
        default="polychromatic",
        blank=True,
        help_text="Color harmony rule for palette generation and theme consistency.",
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
        help_text="Tolerance for amount matching in tenant's currency (e.g., 1.00 units difference allowed)."
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
        help_text="Amount tolerance when matching by amount + date, in tenant's currency (default: 1.00)."
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
                field = cls._meta.get_field("video_background")
                with connection.schema_editor() as schema_editor:
                    schema_editor.add_field(cls, field)
            except (FieldDoesNotExist, OperationalError, DatabaseError, RuntimeError, TypeError, ValueError):
                try:
                    connection.rollback()
                except DatabaseError:
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
        report_style_app = "runtime_blueprints" if django_apps.is_installed("apps.runtime_blueprints") else "siteconfig"
        fk_guards = (
            ("theme_pack", "brand_experience", "ThemePack"),
            ("admin_theme_pack", "brand_experience", "ThemePack"),
            ("teacher_theme_pack", "brand_experience", "ThemePack"),
            ("parent_theme_pack", "brand_experience", "ThemePack"),
            ("default_term_report_style", report_style_app, "ReportCardStyle"),
            ("default_annual_report_style", report_style_app, "ReportCardStyle"),
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

    def _optimize_branding_assets(self) -> None:
        """Optimize image-backed branding assets before persisting changes."""
        for field_name in ("logo", "background_image", "favicon", "sidebar_icon"):
            field = getattr(self, field_name, None)
            if not isinstance(field, FieldFile) or not getattr(field, "name", None):
                continue
            try:
                file_handle = field.file
            except (FileNotFoundError, OSError, ValueError):
                logger.warning(
                    "Skipping branding asset optimization for missing file",
                    extra={"field_name": field_name, "field_path": getattr(field, "name", "")},
                )
                continue
            if getattr(file_handle, "_optimized", False):
                continue
            optimized = optimize_image(field)
            if not optimized:
                continue
            optimized._optimized = True
            field.save(field.name, optimized, save=False)

    def _normalize_update_field_names(
        self,
        update_fields: list[str] | tuple[str, ...] | set[str] | None,
    ) -> set[str]:
        """Normalize update_fields to concrete model field names for ownership classification."""
        normalized: set[str] = set()
        for field_name in update_fields or ():
            if not field_name:
                continue
            try:
                normalized.add(self._meta.get_field(field_name).name)
                continue
            except FieldDoesNotExist:
                pass
            if str(field_name).endswith("_id"):
                try:
                    normalized.add(self._meta.get_field(str(field_name)[:-3]).name)
                except FieldDoesNotExist:
                    continue
        return normalized

    def runtime_sync_owners(
        self,
        *,
        update_fields: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> tuple[str, ...]:
        """
        Return the owner domains that must be synced into RuntimeDefaults.

        The legacy SiteSettings singleton remains the compatibility write-surface,
        but runtime-facing domains should immediately publish into RuntimeDefaults.
        """
        skip_domains = {"safe_platform_default", "delete"}
        if update_fields is None:
            return tuple(owner for owner in OWNERSHIP_DOMAINS if owner not in skip_domains)

        owners = {
            classify_site_settings_field(field_name)
            for field_name in self._normalize_update_field_names(update_fields)
        }
        owners.difference_update(skip_domains)
        return tuple(sorted(owner for owner in owners if owner in OWNERSHIP_DOMAINS))

    def sync_runtime_defaults(
        self,
        *,
        owners: list[str] | tuple[str, ...] | set[str] | None = None,
        exclude_owners: list[str] | tuple[str, ...] | set[str] | None = None,
    ):
        """Publish the relevant SiteSettings owner domains into RuntimeDefaults."""
        effective_owners = tuple(
            owner for owner in (owners or ()) if owner not in {"safe_platform_default", "delete"}
        )
        if owners is not None and not effective_owners:
            return None
        try:
            from apps.platform_runtime.models import RuntimeDefaults

            return RuntimeDefaults.sync_from_site_settings(
                self,
                owners=effective_owners or None,
                exclude_owners=exclude_owners,
            )
        except (AttributeError, ImportError, LookupError, OperationalError, DatabaseError, RuntimeError, TypeError, ValueError):
            return None

    def save(self, *args, **kwargs):
        before = getattr(self, "_orig_backend_feature_flags", {}) or {}
        after = self.backend_feature_flags or {}
        changed_opt_in = (
            before.get("require_guardian_finance_opt_in")
            != after.get("require_guardian_finance_opt_in")
        )
        requested_update_fields = kwargs.get("update_fields")
        cleared_fields = self._sanitize_foreign_keys()
        if requested_update_fields is not None and cleared_fields:
            normalized_update_fields = set(requested_update_fields)
            normalized_update_fields.update(cleared_fields)
            kwargs["update_fields"] = list(normalized_update_fields)
        else:
            normalized_update_fields = None

        self._optimize_branding_assets()

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
                extra={
                    "from": before.get("require_guardian_finance_opt_in"),
                    "to": after.get("require_guardian_finance_opt_in"),
                },
            )

        owners_to_sync = self.runtime_sync_owners(update_fields=normalized_update_fields)
        if owners_to_sync:
            self.sync_runtime_defaults(owners=owners_to_sync)

        self._orig_backend_feature_flags = after.copy()

    @classmethod
    def owned_field_names(
        cls,
        owner: str | None = None,
        *,
        exclude_owners: set[str] | None = None,
    ) -> list[str]:
        """Return concrete SiteSettings field names filtered by ownership domain."""
        excluded = set(exclude_owners or set())
        field_names: list[str] = []
        for field in cls._meta.concrete_fields:
            name = getattr(field, "name", "")
            if not name or name == "id":
                continue
            field_owner = classify_site_settings_field(name)
            if owner and field_owner != owner:
                continue
            if field_owner in excluded:
                continue
            field_names.append(name)
        return field_names

    def owned_payload(
        self,
        owner: str | None = None,
        *,
        exclude_owners: set[str] | None = None,
    ) -> dict[str, object]:
        """Return JSON-safe SiteSettings payload filtered to one ownership domain or exclusion set."""
        if owner and owner not in OWNERSHIP_DOMAINS:
            raise ValueError(f"Unknown SiteSettings ownership domain: {owner}")
        excluded = set(exclude_owners or set())
        payload: dict[str, object] = {}
        for name in self.owned_field_names(owner=owner, exclude_owners=excluded):
            field = self._meta.get_field(name)
            attr_name = getattr(field, "attname", name)
            try:
                value = getattr(self, name, None)
            except ObjectDoesNotExist:
                value = getattr(self, attr_name, None)
            payload[name] = _site_settings_json_safe(value)
            if attr_name != name:
                payload[attr_name] = _site_settings_json_safe(getattr(self, attr_name, None))
        return payload

    def get_backend_feature_flags(self) -> dict[str, object]:
        """
        Return the policy-owned backend flags with defaults merged in.

        This is the compatibility read surface for runtime, admin, and context
        code while `backend_feature_flags` is being migrated out of the legacy
        SiteSettings mega-model.
        """
        payload = self.owned_payload(owner="policies_rules")
        raw_flags = payload.get("backend_feature_flags")
        if not isinstance(raw_flags, dict):
            raw_flags = {}
        return {**default_backend_feature_flags(), **raw_flags}

    def get_preview_platform_config(self) -> dict[str, object]:
        """Return preview-platform config from the ownership-scoped payload."""
        payload = self.owned_payload(owner="preview_platform")
        return {
            "preview_mode_enabled": bool(
                payload.get("preview_mode_enabled", getattr(self, "preview_mode_enabled", False))
            ),
            "preview_note": str(
                payload.get("preview_note", getattr(self, "preview_note", "")) or ""
            ),
            "preview_toggle_enabled": bool(
                payload.get(
                    "preview_toggle_enabled",
                    getattr(self, "preview_toggle_enabled", True),
                )
            ),
            "preview_toggle_label": str(
                payload.get(
                    "preview_toggle_label",
                    getattr(self, "preview_toggle_label", "Toggle preview"),
                )
                or "Toggle preview"
            ),
            "preview_banner_text": str(
                payload.get(
                    "preview_banner_text",
                    getattr(self, "preview_banner_text", ""),
                )
                or ""
            ),
        }

    def get_feature_control_settings(self) -> dict[str, object]:
        """
        Return feature-control state through owner-scoped read contracts first.

        This is the compatibility read surface for feature control views/forms
        while the legacy singleton is being decomposed.
        """
        policies_payload = self.owned_payload(owner="policies_rules")
        safe_payload = self.owned_payload(owner="safe_platform_default")
        reports_payload = self.owned_payload(owner="reports")
        documents_payload = self.owned_payload(owner="documents")
        brand_payload = self.owned_payload(owner="brand_experience")
        preview_settings = self.get_preview_platform_config()

        raw_portal_features = _payload_json_object(
            policies_payload,
            self,
            "portal_features",
        )
        portal_features = default_portal_features()
        portal_features.update(
            {
                str(key): bool(value)
                for key, value in raw_portal_features.items()
                if isinstance(key, str)
            }
        )

        return {
            "portal_features": portal_features,
            "backend_feature_flags": self.get_backend_feature_flags(),
            "notification_channels": _payload_string_list(
                policies_payload,
                self,
                "notification_channels",
            ),
            "enable_parent_portal": _payload_bool(
                policies_payload,
                self,
                "enable_parent_portal",
                False,
            ),
            "enable_teacher_portal": _payload_bool(
                policies_payload,
                self,
                "enable_teacher_portal",
                False,
            ),
            "enable_reports_pdf": _payload_bool(
                reports_payload,
                self,
                "enable_reports_pdf",
                True,
            ),
            "report_downloads_enabled": _payload_bool(
                reports_payload,
                self,
                "report_downloads_enabled",
                True,
            ),
            "grade_approval_enabled": _payload_bool(
                policies_payload,
                self,
                "grade_approval_enabled",
                False,
            ),
            "grade_approval_auto_validate": _payload_bool(
                policies_payload,
                self,
                "grade_approval_auto_validate",
                False,
            ),
            "enable_practical_assessment": _payload_bool(
                policies_payload,
                self,
                "enable_practical_assessment",
                False,
            ),
            "enable_concurrent_mark_uploads": _payload_bool(
                policies_payload,
                self,
                "enable_concurrent_mark_uploads",
                False,
            ),
            "maintenance_mode": _payload_bool(
                safe_payload,
                self,
                "maintenance_mode",
                False,
            ),
            "preview_mode_enabled": bool(preview_settings.get("preview_mode_enabled", False)),
            "preview_note": str(preview_settings.get("preview_note", "") or ""),
            "enable_offline_mode": _payload_bool(
                policies_payload,
                self,
                "enable_offline_mode",
                False,
            ),
            "auto_tag_photos_from_exif": _payload_bool(
                documents_payload,
                self,
                "auto_tag_photos_from_exif",
                False,
            ),
            "show_header_search": _payload_bool(
                brand_payload,
                self,
                "show_header_search",
                False,
            ),
            "show_header_notifications": _payload_bool(
                brand_payload,
                self,
                "show_header_notifications",
                False,
            ),
            "show_header_profile_menu": _payload_bool(
                brand_payload,
                self,
                "show_header_profile_menu",
                False,
            ),
            "show_header_theme_toggle": _payload_bool(
                brand_payload,
                self,
                "show_header_theme_toggle",
                False,
            ),
            "enable_whatsapp_parent_portal": _payload_bool(
                policies_payload,
                self,
                "enable_whatsapp_parent_portal",
                False,
            ),
            "enable_whatsapp_staff_portal": _payload_bool(
                policies_payload,
                self,
                "enable_whatsapp_staff_portal",
                False,
            ),
            "reports_require_approved_grades_before_publish": _payload_bool(
                reports_payload,
                self,
                "reports_require_approved_grades_before_publish",
                False,
            ),
            "reports_use_approved_grades_only": _payload_bool(
                reports_payload,
                self,
                "reports_use_approved_grades_only",
                False,
            ),
        }

    def apply_feature_control_state(
        self,
        *,
        portal_features: dict[str, object],
        backend_feature_flags: dict[str, object],
        field_updates: dict[str, object],
    ) -> None:
        """
        Apply feature-control changes through one model-level write contract.

        This keeps console write semantics centralized while the legacy
        `SiteSettings` fields are still being migrated into owner-scoped domains.
        """
        update_fields = [
            "portal_features",
            "backend_feature_flags",
            "updated_at",
        ]
        for field_name, value in field_updates.items():
            if not hasattr(self, field_name):
                continue
            setattr(self, field_name, value)
            update_fields.append(field_name)

        self.portal_features = dict(portal_features)
        self.backend_feature_flags = dict(backend_feature_flags)
        self.save(update_fields=update_fields)

    def get_notification_delivery_settings(self) -> dict[str, object]:
        """
        Return delivery-channel and sender defaults through owner-scoped surfaces.

        Feature toggles and enabled channels belong to policy/feature control,
        while sender identity belongs to marketplace/integration governance.
        """
        feature_settings = self.get_feature_control_settings()
        integration_settings = self.get_marketplace_integration_settings()
        return {
            "notification_channels": list(
                feature_settings.get("notification_channels") or []
            ),
            "email_from_address": str(
                integration_settings.get(
                    "email_from_address",
                    getattr(self, "email_from_address", ""),
                )
                or ""
            ),
        }

    def get_offline_runtime_settings(self) -> dict[str, object]:
        """
        Return offline runtime controls through the policy owner surface first.
        """
        payload = self.owned_payload(owner="policies_rules")
        flags = self.get_backend_feature_flags()
        return {
            "enable_offline_mode": _payload_bool(
                payload,
                self,
                "enable_offline_mode",
                False,
            ),
            "offline_sync_conflict_resolution": _payload_string(
                payload,
                self,
                "offline_sync_conflict_resolution",
                "show_both",
            ).lower(),
            "backend_feature_flags": flags,
        }

    def get_brand_metadata(self) -> dict[str, str]:
        """Return branding/report metadata through ownership-scoped payloads first."""
        brand_payload = self.owned_payload(owner="brand_experience")
        runtime_payload = self.owned_payload(owner="runtime_blueprints")
        registry_payload = self.owned_payload(owner="global_registries")
        return {
            "school_name": _normalized_site_name(
                brand_payload.get("site_name", getattr(self, "site_name", ""))
            ),
            "school_code": _normalized_school_code(
                runtime_payload.get("school_code", getattr(self, "school_code", ""))
            ),
            "country": str(
                registry_payload.get("country", getattr(self, "country", ""))
                or ""
            ),
            "region": str(
                registry_payload.get("region", getattr(self, "region", ""))
                or ""
            ),
            "ministry": str(
                registry_payload.get("ministry", getattr(self, "ministry", ""))
                or ""
            ),
            "tagline": _normalized_tagline(
                brand_payload.get("tagline", getattr(self, "tagline", ""))
            ),
        }

    def get_report_preview_settings(self) -> dict[str, object]:
        """Return report preview defaults through the reports ownership domain."""
        payload = self.owned_payload(owner="reports")
        return {
            "contact_email": _normalized_report_preview_email(
                payload.get(
                    "report_preview_contact_email",
                    getattr(self, "report_preview_contact_email", ""),
                )
            ),
            "contact_phone": _normalized_report_preview_phone(
                payload.get(
                    "report_preview_contact_phone",
                    getattr(self, "report_preview_contact_phone", ""),
                )
            ),
            "footer_note": str(
                payload.get(
                    "report_preview_footer_note",
                    getattr(self, "report_preview_footer_note", ""),
                )
                or ""
            ),
            "default_report_type": str(
                payload.get(
                    "default_report_preview_type",
                    getattr(self, "default_report_preview_type", REPORT_CARD_TYPE_TERM),
                )
                or REPORT_CARD_TYPE_TERM
            ),
            "default_term_report_style_id": payload.get(
                "default_term_report_style_id",
                getattr(self, "default_term_report_style_id", None),
            ),
            "default_annual_report_style_id": payload.get(
                "default_annual_report_style_id",
                getattr(self, "default_annual_report_style_id", None),
            ),
        }

    def get_theme_experience_settings(self) -> dict[str, object]:
        """
        Return theme/experience values through ownership-scoped payloads first.

        This keeps theme studio, admin, and runtime preview paths aligned on one
        read contract while fields are migrated away from the legacy singleton.
        """
        brand_payload = self.owned_payload(owner="brand_experience")
        preview_payload = self.owned_payload(owner="preview_platform")
        runtime_payload = self.owned_payload(owner="runtime_blueprints")
        reports_payload = self.owned_payload(owner="reports")
        return {
            "primary_color": _payload_string(brand_payload, self, "primary_color", "#0d6efd"),
            "accent_color": _payload_string(brand_payload, self, "accent_color", "#198754"),
            "header_bg_color": _payload_string(brand_payload, self, "header_bg_color", "#0f172a"),
            "footer_bg_color": _payload_string(brand_payload, self, "footer_bg_color", "#0f172a"),
            "success_color": _payload_string(brand_payload, self, "success_color", "#22c55e"),
            "warning_color": _payload_string(brand_payload, self, "warning_color", "#f59e0b"),
            "danger_color": _payload_string(brand_payload, self, "danger_color", "#ef4444"),
            "theme_brightness": _payload_string(brand_payload, self, "theme_brightness", "light"),
            "use_dark_mode": _payload_bool(brand_payload, self, "use_dark_mode", False),
            "theme_pack_id": brand_payload.get("theme_pack_id", getattr(self, "theme_pack_id", None)),
            "admin_theme_pack_id": brand_payload.get(
                "admin_theme_pack_id",
                getattr(self, "admin_theme_pack_id", None),
            ),
            "teacher_theme_pack_id": brand_payload.get(
                "teacher_theme_pack_id",
                getattr(self, "teacher_theme_pack_id", None),
            ),
            "parent_theme_pack_id": brand_payload.get(
                "parent_theme_pack_id",
                getattr(self, "parent_theme_pack_id", None),
            ),
            "skip_theme_publish_guard": _payload_bool(
                preview_payload,
                self,
                "skip_theme_publish_guard",
                False,
            ),
            "admin_use_site_primary": _payload_bool(
                brand_payload,
                self,
                "admin_use_site_primary",
                False,
            ),
            "backend_console_theme": _payload_string(
                brand_payload,
                self,
                "backend_console_theme",
                "",
            ),
            "secondary_font": _payload_string(brand_payload, self, "secondary_font", ""),
            "use_secondary_font_for_headings": _payload_bool(
                brand_payload,
                self,
                "use_secondary_font_for_headings",
                False,
            ),
            "theme_harmony": _payload_string(brand_payload, self, "theme_harmony", "polychromatic"),
            "base_font_size": _payload_int(brand_payload, self, "base_font_size", 16),
            "default_dashboard_view": _payload_string(
                runtime_payload,
                self,
                "default_dashboard_view",
                "",
            ),
            "default_refresh_rate": _payload_int(
                runtime_payload,
                self,
                "default_refresh_rate",
                60,
            ),
            "report_downloads_enabled": _payload_bool(
                reports_payload,
                self,
                "report_downloads_enabled",
                True,
            ),
            "default_term_report_style_id": reports_payload.get(
                "default_term_report_style_id",
                getattr(self, "default_term_report_style_id", None),
            ),
            "default_annual_report_style_id": reports_payload.get(
                "default_annual_report_style_id",
                getattr(self, "default_annual_report_style_id", None),
            ),
        }

    def get_report_style_selection_ids(self) -> dict[str, int | None]:
        """Return report style ids through the reports owner surface first."""
        settings = self.get_theme_experience_settings()
        return {
            "default_term_report_style_id": settings.get("default_term_report_style_id"),
            "default_annual_report_style_id": settings.get("default_annual_report_style_id"),
        }

    def get_finance_runtime_config(self) -> dict[str, object]:
        """Return finance automation, reminder, and receipt policy through the policy owner domain."""
        payload = self.owned_payload(owner="policies_rules")
        return {
            "auto_generate_invoices_enabled": _payload_bool(
                payload, self, "finance_auto_generate_invoices_enabled", False
            ),
            "auto_generate_schedule": _payload_json_object(
                payload, self, "finance_auto_generate_schedule"
            ),
            "auto_generate_due_date_offset_days": _payload_int(
                payload, self, "finance_auto_generate_due_date_offset_days", 30
            ),
            "auto_generate_require_approval": _payload_bool(
                payload, self, "finance_auto_generate_require_approval", False
            ),
            "fee_plan_auto_copy_enabled": _payload_bool(
                payload, self, "finance_fee_plan_auto_copy_enabled", False
            ),
            "fee_plan_auto_copy_mode": _payload_string(
                payload, self, "finance_fee_plan_auto_copy_mode", "manual"
            ).lower(),
            "fee_plan_copy_increase_percentage": _payload_decimal(
                payload, self, "finance_fee_plan_copy_increase_percentage", "0.00"
            ),
            "payment_reminder_default_channels": _payload_string_list(
                payload, self, "finance_payment_reminder_default_channels"
            ),
            "payment_reminder_default_days": _payload_int_list(
                payload, self, "finance_payment_reminder_default_days"
            ),
            "invoice_auto_status_updates_enabled": _payload_bool(
                payload, self, "finance_invoice_auto_status_updates_enabled", True
            ),
            "invoice_overdue_grace_period_days": _payload_int(
                payload, self, "finance_invoice_overdue_grace_period_days", 0
            ),
            "receipt_verification_method": _payload_string(
                payload, self, "finance_receipt_verification_method", "pattern"
            ),
            "receipt_upload_enabled": _payload_bool(
                payload, self, "finance_receipt_upload_enabled", True
            ),
            "receipt_auto_verify_enabled": _payload_bool(
                payload, self, "finance_receipt_auto_verify_enabled", True
            ),
            "receipt_max_size_mb": _payload_int(
                payload, self, "finance_receipt_max_size_mb", 5
            ),
            "receipt_allowed_extensions": _payload_string(
                payload, self, "finance_receipt_allowed_extensions", "pdf,jpg,jpeg,png"
            ).strip().lower(),
            "receipt_idempotency_window_minutes": _payload_int(
                payload, self, "finance_receipt_idempotency_window_minutes", 10
            ),
            "receipt_auto_apply_threshold": _payload_float(
                payload, self, "finance_receipt_auto_apply_threshold", 0.9
            ),
            "receipt_auto_apply_enabled": _payload_bool(
                payload, self, "finance_receipt_auto_apply_enabled", True
            ),
            "receipt_require_admin_approval": _payload_bool(
                payload, self, "finance_receipt_require_admin_approval", False
            ),
            "receipt_amount_tolerance": _payload_decimal(
                payload, self, "finance_receipt_amount_tolerance", "1.00"
            ),
            "bank_verification_enabled": _payload_bool(
                payload, self, "finance_bank_verification_enabled", True
            ),
            "bank_verification_auto_approve": _payload_bool(
                payload, self, "finance_bank_verification_auto_approve", False
            ),
            "bank_verification_tolerance_days": _payload_int(
                payload, self, "finance_bank_verification_tolerance_days", 7
            ),
            "bank_verification_amount_tolerance": _payload_decimal(
                payload, self, "finance_bank_verification_amount_tolerance", "100.00"
            ),
            "payment_instructions_bank": _payload_string(
                payload, self, "finance_payment_instructions_bank", ""
            ),
            "payment_instructions_mtn_momo": _payload_string(
                payload, self, "finance_payment_instructions_mtn_momo", ""
            ),
            "payment_instructions_orange_money": _payload_string(
                payload, self, "finance_payment_instructions_orange_money", ""
            ),
            "payment_instructions_cash": _payload_string(
                payload, self, "finance_payment_instructions_cash", ""
            ),
            "receipt_upload_instructions": _payload_string(
                payload, self, "finance_receipt_upload_instructions", ""
            ),
            "reminder_no_contact_action": _payload_string(
                payload, self, "finance_reminder_no_contact_action", "warn_only"
            ),
            "reminder_retry_failed_hours": _payload_int(
                payload, self, "finance_reminder_retry_failed_hours", 24
            ),
            "reminder_max_retries": _payload_int(
                payload, self, "finance_reminder_max_retries", 2
            ),
        }

    def get_marketplace_integration_settings(self) -> dict[str, object]:
        """Return integration-owned defaults through the marketplace/integration owner domain."""
        payload = self.owned_payload(owner="marketplace_integrations")
        return {
            "marksheet_ocr_command": _payload_string(
                payload, self, "marksheet_ocr_command", ""
            ),
            "sms_provider": _payload_string(payload, self, "sms_provider", "console"),
            "sms_api_key": _payload_string(payload, self, "sms_api_key", ""),
            "sms_sender_id": _payload_string(payload, self, "sms_sender_id", "RUNMYCAMPUS"),
            "email_from_address": _payload_string(
                payload, self, "email_from_address", "noreply@school.example.com"
            ),
            "whatsapp_support_number": _payload_string(
                payload, self, "whatsapp_support_number", ""
            ),
            "whatsapp_admissions_number": _payload_string(
                payload, self, "whatsapp_admissions_number", ""
            ),
        }

    def get_support_contact_settings(self) -> dict[str, str]:
        """Return support/contact settings through owner-scoped brand and integration surfaces."""
        brand_payload = self.owned_payload(owner="brand_experience")
        integration_settings = self.get_marketplace_integration_settings()
        return {
            "company_phone": _payload_string(
                brand_payload,
                self,
                "company_phone",
                "",
            ),
            "company_email": _payload_string(
                brand_payload,
                self,
                "company_email",
                "",
            ),
            "footer_whatsapp_url": _payload_string(
                brand_payload,
                self,
                "footer_whatsapp_url",
                "",
            ),
            "whatsapp_support_number": str(
                integration_settings.get("whatsapp_support_number", "") or ""
            ),
            "whatsapp_admissions_number": str(
                integration_settings.get("whatsapp_admissions_number", "") or ""
            ),
        }

    def get_theme_selection_ids(self) -> dict[str, int | None]:
        """Return theme-pack foreign key ids through the brand-experience ownership domain."""
        settings = self.get_theme_experience_settings()
        return {
            "theme_pack_id": settings.get("theme_pack_id"),
            "admin_theme_pack_id": settings.get("admin_theme_pack_id"),
            "teacher_theme_pack_id": settings.get("teacher_theme_pack_id"),
            "parent_theme_pack_id": settings.get("parent_theme_pack_id"),
        }

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

    def resolve_default_report_style(self, report_type: str) -> "ReportCardStyle | None":
        """Resolve the default report style through the owner surface first, then fallback to active defaults."""
        field_name = "default_term_report_style" if report_type == REPORT_CARD_TYPE_TERM else "default_annual_report_style"
        selection_ids = self.get_report_style_selection_ids()
        style_id = (
            selection_ids.get("default_term_report_style_id")
            if report_type == REPORT_CARD_TYPE_TERM
            else selection_ids.get("default_annual_report_style_id")
        )
        owner_model = get_report_card_style_owner_model()
        if style_id:
            try:
                style = owner_model.objects.filter(pk=style_id).first()
            except (OperationalError, DatabaseError):
                style = None
            if style and style.is_active:
                self._state.fields_cache[field_name] = style
                return style
            if style is None:
                self._sanitize_foreign_keys(persist=True)
        try:
            return owner_model.objects.active().first()
        except (AttributeError, OperationalError, DatabaseError):
            return None

    @property
    def active_theme(self) -> "ThemePack | None":
        theme_pack_model = get_theme_pack_owner_model()
        selection_ids = self.get_theme_selection_ids()
        theme_pack_id = selection_ids.get("theme_pack_id")
        if theme_pack_id:
            try:
                selected = theme_pack_model.objects.filter(pk=theme_pack_id).first()
            except (OperationalError, DatabaseError):
                return None
            if selected:
                self._state.fields_cache["theme_pack"] = selected
                return selected
            self._sanitize_foreign_keys(persist=True)
        try:
            fallback = theme_pack_model.objects.filter(is_default=True, is_active=True).first()
            if fallback:
                return fallback
            return theme_pack_model.objects.filter(is_active=True).order_by("name").first()
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

    def apply_theme_experience_state(
        self,
        *,
        field_updates: dict[str, object],
        save: bool = True,
    ) -> None:
        """
        Persist Theme Studio changes through one owner-scoped write contract.

        The underlying fields still live on the legacy singleton during the
        migration, but Theme Studio should not be mutating them ad hoc from the
        form layer.
        """
        allowed_fields = {
            "primary_color",
            "accent_color",
            "header_bg_color",
            "footer_bg_color",
            "success_color",
            "warning_color",
            "danger_color",
            "theme_brightness",
            "use_dark_mode",
            "theme_pack",
            "admin_theme_pack",
            "teacher_theme_pack",
            "parent_theme_pack",
            "theme_harmony",
            "admin_use_site_primary",
            "skip_theme_publish_guard",
            "backend_console_theme",
            "secondary_font",
            "use_secondary_font_for_headings",
            "base_font_size",
            "default_widgets_per_role",
            "report_downloads_enabled",
            "default_dashboard_view",
            "default_refresh_rate",
            "default_term_report_style",
            "default_annual_report_style",
        }
        update_fields: list[str] = []
        for field_name, value in field_updates.items():
            if field_name not in allowed_fields or not hasattr(self, field_name):
                continue
            setattr(self, field_name, value)
            update_fields.append(field_name)
        if save and update_fields:
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
        theme_pack_model = get_theme_pack_owner_model()
        selection_ids = self.get_theme_selection_ids()
        admin_theme_pack_id = selection_ids.get("admin_theme_pack_id")
        if admin_theme_pack_id:
            try:
                admin_pack = theme_pack_model.objects.filter(pk=admin_theme_pack_id).first()
            except (OperationalError, DatabaseError):
                admin_pack = None
            if admin_pack and admin_pack.is_active and admin_pack.applies_to_admin:
                self._state.fields_cache["admin_theme_pack"] = admin_pack
                return admin_pack
            if admin_pack is None:
                self._sanitize_foreign_keys(persist=True)

        site_pack = None
        site_theme_pack_id = selection_ids.get("theme_pack_id")
        if site_theme_pack_id:
            try:
                site_pack = theme_pack_model.objects.filter(pk=site_theme_pack_id).first()
            except (OperationalError, DatabaseError):
                site_pack = None
            if site_pack and site_pack.is_active and getattr(site_pack, "applies_to_admin", False):
                self._state.fields_cache["theme_pack"] = site_pack
                return site_pack
            if site_pack is None:
                self._sanitize_foreign_keys(persist=True)
        try:
            fallback = theme_pack_model.objects.filter(applies_to_admin=True, is_active=True).order_by("-is_default", "name").first()
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
        theme_pack_model = get_theme_pack_owner_model()
        selection_ids = self.get_theme_selection_ids()
        teacher_theme_pack_id = selection_ids.get("teacher_theme_pack_id")
        parent_theme_pack_id = selection_ids.get("parent_theme_pack_id")
        if role == "TEACHER" and teacher_theme_pack_id:
                try:
                    pack = theme_pack_model.objects.filter(
                        pk=teacher_theme_pack_id, is_active=True
                    ).first()
                    if pack:
                        return pack
                except (OperationalError, DatabaseError):
                    pass
        if role == "PARENT" and parent_theme_pack_id:
                try:
                    pack = theme_pack_model.objects.filter(
                        pk=parent_theme_pack_id, is_active=True
                    ).first()
                    if pack:
                        return pack
                except (OperationalError, DatabaseError):
                    pass
        return self.active_theme


from .models_tooling import (  # noqa: F401
    FormDraft,
    Integration,
    OfficialReportTemplate,
    ReportCardStyle,
    ReportCardStyleQuerySet,
    ReportTemplate,
    ThemePack,
    UserPreference,
    get_report_card_style_for_student,
)  # noqa: F401


# ============================================================================
# Phase 1.2.4: Internationalization & Multi-Region Support
# ============================================================================



# AI models moved to .models_ai for Phase 10 — 2.1 giant-file decomposition. Re-export for backward compatibility.

# Platform catalog and global experience models: re-export so "from apps.siteconfig.models import ..." works
# (global_registries, admin, and others rely on this).
from .models_platform_catalog import (  # noqa: F401
    BillingWaiverAuditLog,
    CountryMultiplier,
    CustomFeatureTicket,
    CustomNuance,
    EducationSystemProfile,
    FeatureFragment,
    PendingNuance,
    Plan,
    PlanAddon,
    Province,
    RegionConfig,
    RevenueSnapshot,
    ServiceIntegration,
    SystemFeature,
    TenantSystem,
    WaiverRequest,
    WebhookSubscription,
    default_education_term_labels,
    default_education_subject_seed,
    get_feature_fragment_cap,
)  # noqa: F401
from .models_global_experience import (  # noqa: F401
    BrandProfile,
    BrandSettings,
    DesignTemplate,
    GlobalBrandRegistry,
    GradingScaleConfig,
    WeatherLocation,
)  # noqa: F401
from .models_feature_controls import (  # noqa: F401
    FeatureToggleDefinition,
    FeatureToggleState,
    GlobalSupportTicket,
    TourStep,
)  # noqa: F401
# Re-export for admin/forms: models live in academics (moved in 0146 / tenant_runtime).
from apps.academics.models import ReportCardStyleAssignment  # noqa: F401
from apps.academics.models_tenant_runtime import HolidayCalendar  # noqa: F401
from .models_metadata_catalog import DynamicFieldDefinition, DynamicFieldValue  # noqa: F401
from .models_platform_catalog import TenantAdmissionNumberPolicy  # noqa: F401
from .models_ai import (  # noqa: F401
    AIGatewayMetric,
    AIEmbeddingStore,
    AIModelRegistry,
    AIPromptRegistry,
    RegionalAIConfig,
)  # noqa: F401
from .models_feature_controls import FeatureUsageEvent  # noqa: F401
from .models_runtime_ops import BreakGlassOverride, BroadcastCampaign  # noqa: F401
from .models_marketing import ProductFeedback, MarketingContent, BlogPost  # noqa: F401
from .models_global_experience import GlobalSyllabus, LearningPassport  # noqa: F401


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


post_save.connect(_refresh_site_settings_cache, sender=SiteSettings)
post_save.connect(_emit_global_change_alert, sender=SiteSettings)
post_delete.connect(_clear_site_settings_cache, sender=SiteSettings)

