from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.apps import apps as django_apps

from apps.accounts.models import User
from apps.academics.models import Classroom, Subject
from apps.finance.models import ComplianceProfile, Invoice, Payment
from apps.people.models import StudentProfile, TeacherProfile, StudentGuardian
from apps.reports.models import ReportCard

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
    FINANCE = "FINANCE", "Finances"
    ACADEMICS = "ACADEMICS", "Academics"
    ATTENDANCE = "ATTENDANCE", "Attendance"
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
    ],
}


def default_dashboard_widgets(role: str | None) -> list[str]:
    role_key = (role or "").upper()
    return list(ROLE_WIDGET_DEFAULTS.get(role_key, [key for key, _ in DASHBOARD_WIDGET_OPTIONS]))


def get_dashboard_widget_choices(role: str | None) -> list[tuple[str, str]]:
    allowed = set(default_dashboard_widgets(role))
    return [(key, label) for key, label in DASHBOARD_WIDGET_OPTIONS if key in allowed]


def resolve_dashboard_widgets(role: str | None, preference: "UserPreference | None" = None) -> list[str]:
    allowed = default_dashboard_widgets(role)
    if preference:
        if preference.dashboard_view == DashboardView.CUSTOM and preference.dashboard_widgets:
            selected = [key for key in preference.dashboard_widgets if key in allowed]
            return selected or allowed
        view_map = {
            DashboardView.FINANCE: ["finance", "events", "communications", "links"],
            DashboardView.ATTENDANCE: ["attendance", "events", "tasks", "links"],
            DashboardView.ACADEMICS: ["performance", "completion", "upcoming", "analytics", "tasks", "links"],
        }
        mapped = view_map.get(preference.dashboard_view)
        if mapped:
            filtered = [key for key in mapped if key in allowed]
            return filtered or allowed
    return allowed


class SiteSettings(models.Model):
    # Branding
    site_name = models.CharField(max_length=120, default="Gilead School System")
    tagline = models.CharField(max_length=200, blank=True, default="Knowledge ƒ?› Technology ƒ?› Excellence")
    logo = models.ImageField(upload_to="branding/", blank=True, null=True)
    background_image = models.ImageField(upload_to="branding/bg/", blank=True, null=True)
    brand_font = models.CharField(max_length=120, default="Inter, system-ui, sans-serif")
    school_code = models.CharField(
        max_length=20,
        default="GIL",
        help_text="Short code used in admission numbers (e.g., GIL).",
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
    use_dark_mode = models.BooleanField(default=False)
    custom_css = models.TextField(blank=True)
    theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_settings",
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

    # Feature toggles
    enable_parent_portal = models.BooleanField(default=True)
    enable_teacher_portal = models.BooleanField(default=True)
    enable_reports_pdf = models.BooleanField(default=True)
    report_downloads_enabled = models.BooleanField(default=True)
    portal_features = models.JSONField(default=default_portal_features, blank=True)
    social_links = models.JSONField(default=default_social_links, blank=True)
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
        ComplianceProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_settings",
    )

    class DeadlineMode(models.TextChoices):
        TERM_END = "TERM_END", "Term end date"
        CUSTOM_DEADLINE = "CUSTOM_DEADLINE", "Custom deadline"
        PUBLISH_DATE = "PUBLISH_DATE", "Publish date"

    # Analytics defaults
    top_students_default_limit = models.PositiveSmallIntegerField(default=10)
    pass_mark = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    use_promotion_rule_for_pass = models.BooleanField(default=False)
    weak_subject_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    improvement_delta_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    deadline_mode = models.CharField(
        max_length=20,
        choices=DeadlineMode.choices,
        default=DeadlineMode.TERM_END,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"

    def __str__(self) -> str:
        return self.site_name

    @classmethod
    def get_solo(cls) -> "SiteSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def active_theme(self) -> "ThemePack | None":
        if self.theme_pack:
            return self.theme_pack
        return ThemePack.objects.filter(is_default=True, is_active=True).first()

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
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
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
    Generic external integration registry (plugin-style).
    Examples: Email (SMTP/SendGrid), SMS (Twilio), Payments (Stripe), Analytics (GA/Sentry).
    """

    PROVIDERS = [
        ("email", "Email"),
        ("sms", "SMS"),
        ("payments", "Payments"),
        ("analytics", "Analytics"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=120)
    provider = models.CharField(max_length=30, choices=PROVIDERS, default="other")
    enabled = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.provider})"


class UserPreference(models.Model):
    class NotificationChannel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        APP = "APP", "App"

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


class ReportCardStyleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ReportCardStyle(models.Model):
    TERM_TEMPLATE_CHOICES = [
        ("reports/term_report.html", "Standard term template"),
        ("reports/term_report_cameroon.html", "Cameroon term template"),
    ]
    ANNUAL_TEMPLATE_CHOICES = [
        ("reports/annual_report.html", "Standard annual template"),
        ("reports/annual_report_cameroon.html", "Cameroon annual template"),
    ]

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    term_template = models.CharField(max_length=120, choices=TERM_TEMPLATE_CHOICES, default=TERM_TEMPLATE_CHOICES[0][0])
    annual_template = models.CharField(max_length=120, choices=ANNUAL_TEMPLATE_CHOICES, default=ANNUAL_TEMPLATE_CHOICES[0][0])
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    watermark_text = models.CharField(max_length=150, blank=True)
    header_tagline = models.CharField(max_length=200, blank=True)
    css_snippet = models.TextField(blank=True)
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

