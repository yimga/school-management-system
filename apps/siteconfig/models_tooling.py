from __future__ import annotations

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.academics.models import Subject
from apps.people.models import StudentProfile

from .image_utils import optimize_image
from .svg_sanitize import validate_svg_safe
from .models_constants import (
    BACKEND_CONSOLE_THEME_CHOICES,
    LOGO_BG_MODE_CHOICES,
    REPORT_CARD_TYPE_TERM,
)
from .models_support import (
    DashboardView,
    ThemeLayout,
    get_report_card_style_owner_model,
)


class ThemePack(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    background_color = models.CharField(max_length=20, default="#ffffff")
    font_family = models.CharField(
        max_length=120, default="Inter, system-ui, sans-serif"
    )
    layout = models.CharField(
        max_length=20, choices=ThemeLayout.choices, default=ThemeLayout.STANDARD
    )
    custom_css = models.TextField(blank=True)
    palette = models.JSONField(default=dict, blank=True)
    logo = models.ImageField(
        upload_to="branding/themepack/logo/",
        blank=True,
        null=True,
        help_text="Optional: Logo for this theme pack.",
        validators=[validate_svg_safe],
    )
    background_image = models.ImageField(
        upload_to="branding/themepack/bg/",
        blank=True,
        null=True,
        help_text="Optional: Background image for this theme pack.",
    )
    video_background = models.FileField(
        upload_to="branding/themepack/video/",
        blank=True,
        null=True,
        help_text="Optional: Video background for this theme pack.",
    )
    svg_background = models.FileField(
        upload_to="branding/themepack/svg/",
        blank=True,
        null=True,
        help_text="Optional: SVG background for this theme pack.",
    )
    logo_opacity = models.FloatField(
        default=0.3,
        blank=True,
        null=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Opacity for theme logo background (0.0 = transparent, 1.0 = opaque)",
    )
    logo_background_mode = models.CharField(
        max_length=16,
        choices=LOGO_BG_MODE_CHOICES,
        default="contain",
        help_text="How the theme logo background image is displayed.",
    )
    applies_to_admin = models.BooleanField(
        default=False,
        help_text="Use this pack for the Django /admin interface.",
    )
    backend_console_theme = models.CharField(
        max_length=20,
        choices=BACKEND_CONSOLE_THEME_CHOICES,
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

    def clean(self):
        """Reject theme packs whose colors are invalid or an invisible brand.

        Foreground text stays readable at render time via the adaptive
        ``--text-on-brand`` cascade, so we only guard the two things adaptation
        cannot fix: each color must be valid hex, and the primary color must be
        visibly distinct from the canvas (or the brand vanishes into it).
        """
        super().clean()
        from apps.siteconfig.contrast_guard import contrast_ratio, hex_to_rgb

        errors = {}
        for field in ("primary_color", "accent_color", "background_color"):
            try:
                hex_to_rgb((getattr(self, field) or "").strip())
            except (ValueError, TypeError):
                errors[field] = _("Enter a valid hex color, e.g. #4f46e5.")
        if errors:
            raise ValidationError(errors)
        if contrast_ratio(self.primary_color, self.background_color) < 1.3:
            raise ValidationError(
                {
                    "primary_color": _(
                        "Choose a primary color that stands out from the background."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if (
            self.logo
            and hasattr(self.logo, "file")
            and not getattr(self.logo.file, "_optimized", False)
        ):
            optimized = optimize_image(self.logo)
            if optimized:
                optimized._optimized = True
                self.logo.save(self.logo.name, optimized, save=False)
        if (
            self.background_image
            and hasattr(self.background_image, "file")
            and not getattr(self.background_image.file, "_optimized", False)
        ):
            optimized = optimize_image(self.background_image)
            if optimized:
                optimized._optimized = True
                self.background_image.save(
                    self.background_image.name, optimized, save=False
                )
        if self.is_default:
            ThemePack.objects.exclude(pk=self.pk).filter(is_default=True).update(
                is_default=False
            )
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
    category = models.CharField(
        max_length=20, choices=CATEGORIES, default="OTHER", blank=True
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Master kill switch: when False, this integration is not used (payments, email, portal links).",
    )
    config = models.JSONField(default=dict, blank=True)
    rate_limit_per_min = models.PositiveIntegerField(null=True, blank=True)
    ip_whitelist = models.JSONField(default=list, blank=True)
    allowed_scopes = models.JSONField(default=dict, blank=True)
    secret_key_hash = models.TextField(blank=True)
    last_call_at = models.DateTimeField(null=True, blank=True)
    health_status = models.CharField(
        max_length=20, choices=HEALTH_STATUS, default="healthy", blank=True
    )
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
    student_model = django_apps.get_model("people", "StudentProfile")
    headers = [
        "Student Code",
        "Name",
        "Academic Year",
        "Classroom",
        "Specialty",
        "Active",
    ]
    rows = []
    qs = student_model.objects.select_related("classroom", "specialty")
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
    teacher_model = django_apps.get_model("people", "TeacherProfile")
    headers = ["Username", "Full Name", "Department", "Position", "Payment Method"]
    rows = []
    qs = teacher_model.objects.select_related("department", "user")
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
    rows = [
        [subject.name, subject.get_category_display()]
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        for subject in Subject.objects.all()
    ]
    return headers, rows


@report_exporter("fee_payments")
def _payment_export():
    payment_model = django_apps.get_model("finance", "Payment")
    headers = ["Student", "Invoice", "Amount", "Method", "Paid At", "Receipt"]
    rows = []
    qs = payment_model.objects.select_related("invoice__student")
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
    class SubSystem(models.TextChoices):
        FR = "FR", "French sub-system"
        EN = "EN", "English sub-system"
        INT = "INT", "International"

    region_code = models.CharField(max_length=20, blank=True, help_text="e.g. CMR")
    sub_system = models.CharField(
        max_length=10, choices=SubSystem.choices, default=SubSystem.EN
    )
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
        (
            "reports/annual_report_cameroon_modern.html",
            "Cameroon annual template (modern)",
        ),
    ]

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    term_template = models.CharField(
        max_length=120,
        choices=TERM_TEMPLATE_CHOICES,
        default=TERM_TEMPLATE_CHOICES[0][0],
    )
    annual_template = models.CharField(
        max_length=120,
        choices=ANNUAL_TEMPLATE_CHOICES,
        default=ANNUAL_TEMPLATE_CHOICES[0][0],
    )
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
        validators=[validate_svg_safe],
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
            'Example: {"report_title": "ACADEMIC REPORT SHEET", "rank": "Rank"}.'
        ),
    )
    layout_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Layout configuration for report templates (show/hide columns/sections). "
            'Example: {"show_school_rank": true, "show_specialty_rank": true}.'
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
        data = self.labels or {}
        value = data.get(key, default)
        return str(value) if value is not None else default

    def flag(self, key: str, default: bool = False) -> bool:
        data = self.layout_config or {}
        value = data.get(key, default)
        return bool(value) if value is not None else bool(default)


from apps.academics.models import ReportCardStyleAssignment  # noqa: E402,F401


def get_report_card_style_for_student(
    student: StudentProfile, report_type: str
) -> ReportCardStyle | None:
    if not student or not student.classroom:
        return None
    assignment = getattr(student.classroom, "report_card_style_assignment", None)
    if assignment and assignment.style and assignment.style.is_active:
        return assignment.style

    from apps.siteconfig.config_service import get_effective_site_settings

    # config-resolver-allow: resolve_default_report_style() method invoked on the settings namespace, not a plain key read
    site = get_effective_site_settings(school=getattr(student, "school", None))
    style = site.resolve_default_report_style(report_type) if site else None
    if style and style.is_active:
        return style

    return get_report_card_style_owner_model().objects.active().first()
