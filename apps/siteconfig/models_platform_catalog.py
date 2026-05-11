from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .models import tenant_upload_to_waiver_requests


class RegionConfig(models.Model):
    CALENDAR_CHOICES = [
        ("gregorian", "Gregorian"),
        ("islamic", "Islamic"),
        ("buddhist", "Buddhist"),
        ("hebrew", "Hebrew"),
    ]
    GRADING_SCALE_CHOICES = [
        ("0-20", "Cameroon (0-20)"),
        ("0-100", "US/UK (0-100)"),
        ("0-10", "European (0-10)"),
        ("a-f", "Letter Grade (A-F)"),
        ("gpa", "GPA (0-4.0)"),
    ]

    code = models.CharField(
        max_length=10,
        unique=True,
        primary_key=True,
        help_text="ISO country code (CMR, USA, GBR, KEN, NGA, etc.)",
    )
    name = models.CharField(
        max_length=100, help_text="Country/Region name (Cameroon, United States, etc.)"
    )
    default_language = models.CharField(
        max_length=10,
        default="en",
        help_text="Default language code (en, fr, pid, sw, ha)",
    )
    timezone = models.CharField(
        max_length=50,
        default="UTC",
        help_text="Timezone name (Africa/Douala, America/New_York, Europe/London, etc.)",
    )
    decimal_separator = models.CharField(
        max_length=1, default=".", help_text="Decimal separator (. or ,)"
    )
    thousands_separator = models.CharField(
        max_length=1, default=",", help_text="Thousands separator (, or .)"
    )
    date_format = models.CharField(
        max_length=20,
        default="DD/MM/YYYY",
        help_text="Date display format (DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD)",
    )
    calendar_system = models.CharField(
        max_length=20,
        choices=CALENDAR_CHOICES,
        default="gregorian",
    )
    grading_scale = models.CharField(
        max_length=20,
        choices=GRADING_SCALE_CHOICES,
        default="0-100",
    )
    default_currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO currency code (USD, EUR, GBP, XAF, KES, NGN, etc.). Set per-country during onboarding; USD is the neutral fallback.",
    )
    academic_year_start_month = models.IntegerField(
        default=9,
        help_text="Month when academic year starts (1-12). Northern hemisphere typically uses 9 (September); the region engine overrides to 1 (January) for Southern hemisphere countries during onboarding.",
    )
    term_count_per_year = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Number of instructional periods in a school year (1-12).",
    )
    grading_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text='Report card average: {"type": "simple"} or {"type": "coefficient", "scale_max": 20}. Subject coefficients from GradingScaleConfig or school settings.',
    )
    school_registration_number_format = models.CharField(
        max_length=100,
        blank=True,
        help_text="Regex pattern for school registration numbers",
    )
    student_id_format = models.CharField(
        max_length=100,
        blank=True,
        help_text="Format for student IDs (e.g., 'nnnn' for 4 digits)",
    )
    certificate_template_name = models.CharField(
        max_length=100,
        default="standard",
        help_text="Certificate template to use (standard, fancy, minimal, etc.)",
    )
    enable_online_admissions = models.BooleanField(
        default=True,
        help_text="Allow online applications in this region",
    )
    enable_parent_portal = models.BooleanField(
        default=True,
        help_text="Enable parent/guardian access to student information",
    )
    enable_student_portal = models.BooleanField(
        default=True,
        help_text="Enable student self-service portal",
    )
    is_rtl = models.BooleanField(
        default=False,
        help_text='Right-to-left script (Arabic, Hebrew, Urdu). When True, set <html dir="rtl"> from tenant locale.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Region Configurations"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def gradingscaleconfig_set(self):
        return self.grading_scales

    @classmethod
    def get_default(cls):
        region, _ = cls.objects.get_or_create(
            code="GLOBAL",
            defaults={
                "name": "Global Default",
                "default_language": "en",
                "timezone": getattr(settings, "TIME_ZONE", "UTC") or "UTC",
                "date_format": "YYYY-MM-DD",
                "grading_scale": "0-100",
                "default_currency": "USD",
                "academic_year_start_month": 9,
                "term_count_per_year": 3,
            },
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
    sub_system = models.CharField(
        max_length=10, choices=SubSystem.choices, default=SubSystem.ANY
    )
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
        help_text="Default subjects to seed when onboarding a school.",
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
        labels = [
            str(item).strip() for item in (self.term_labels or []) if str(item).strip()
        ]
        if len(labels) >= int(self.term_count_per_year or 0):
            return labels
        labels.extend(
            [
                f"Term {idx + 1}"
                for idx in range(len(labels), int(self.term_count_per_year or 0))
            ]
        )
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
                category = (
                    str(item.get("category") or "GENERAL").strip().upper() or "GENERAL"
                )
                rows.append({"name": name, "category": category})
        if rows:
            return rows
        return default_education_subject_seed()

    @classmethod
    def for_school(cls, school):
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


class Province(models.Model):
    region = models.ForeignKey(
        RegionConfig,
        on_delete=models.CASCADE,
        related_name="provinces",
        help_text="Country (region) this province belongs to.",
    )
    code = models.CharField(
        max_length=32, help_text="Province/state code (e.g. NW, CA)"
    )
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
        return f"{self.school.name} <-> {self.system.name}"


class TenantAdmissionNumberPolicy(models.Model):
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
    seq_width = models.PositiveSmallIntegerField(
        default=4, help_text="Padding width for sequence (e.g. 4 -> 0001)."
    )
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


class Plan(models.Model):
    class BillingModel(models.TextChoices):
        FLAT = "FLAT", "Flat (fixed monthly)"
        PER_STUDENT = "PER_STUDENT", "Per student"
        TIERED = "TIERED", "Tiered (volume bands)"

    name = models.CharField(
        max_length=120, help_text="Plan name (e.g. Basic, Pro, Enterprise)"
    )
    slug = models.SlugField(
        max_length=80, unique=True, help_text="Unique slug (e.g. basic, pro)"
    )
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
        help_text='Tier bands for TIERED model, e.g. [{"max": 500, "price": 200}, {"max": 2000, "price": 600}]',
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


class SyncConflict(models.Model):
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
    entity_type = models.CharField(
        max_length=40, help_text="e.g. student, attendance, classroom"
    )
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


class PlanAddon(models.Model):
    code = models.SlugField(
        max_length=80, unique=True, help_text="Feature code e.g. design_studio"
    )
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
    class Zone(models.TextChoices):
        A = "A", "Zone A (premium)"
        B = "B", "Zone B (standard)"
        C = "C", "Zone C (discounted)"

    country_code = models.CharField(
        max_length=3, unique=True, help_text="ISO 3166-1 alpha-2/3"
    )
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


class RevenueSnapshot(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="revenue_snapshots",
    )
    snapshot_date = models.DateField(
        help_text="First day of the month for this snapshot"
    )
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
        return f"{self.school.name} -> {self.new_billing_type} at {self.created_at}"


class WaiverRequest(models.Model):
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
        return f"{self.school.name} - {self.status}"


class CustomNuance(models.Model):
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
        help_text='JSON-Logic structure (e.g. {"and": [{">": [{"var": "gpa"}, 3.8]}, {"var": "sibling_count"}]}). Only allowed ops run.',
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
        return f"{self.school.name} - {self.get_hook_point_display()}"


class PendingNuance(models.Model):
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
    proposed_logic = models.JSONField(
        default=dict, help_text="JSON-Logic to apply at hook_point"
    )
    human_explanation = models.TextField(
        blank=True, help_text="Plain-language description for reviewer"
    )
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
        return f"{self.school.name} - {self.hook_point} ({self.status})"


class ServiceIntegration(models.Model):
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
    service_name = models.CharField(
        max_length=100, help_text="e.g. Moodle, Stripe, Google Classroom"
    )
    service_type = models.CharField(
        max_length=20, choices=ServiceType.choices, default=ServiceType.OTHER
    )
    client_id = models.CharField(max_length=255, blank=True)
    client_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text="Encrypt at rest in production; use for OAuth/LTI.",
    )
    endpoint_url = models.URLField(
        blank=True, help_text="Base URL for API or launch endpoint"
    )
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
        return f"{self.school.name} - {self.service_name}"


class WebhookSubscription(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="webhook_subscriptions",
    )
    event_type = models.CharField(
        max_length=80, help_text="e.g. exam.completed, fee.paid"
    )
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
        return f"{self.school.name} - {self.event_type} -> {self.target_url}"


class WebhookDelivery(models.Model):
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
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
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
            models.Index(
                fields=["status", "next_attempt_at"],
                name="siteconfig_webhook_queue_idx",
            ),
            models.Index(
                fields=["event_type", "created_at"], name="siteconfig_webhook_event_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "event_id"],
                name="siteconfig_unique_subscription_event_delivery",
            )
        ]

    def __str__(self):
        return (
            f"{self.subscription_id}:{self.event_type}:{self.event_id} [{self.status}]"
        )


class CustomFeatureTicket(models.Model):
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
    upvote_count = models.PositiveIntegerField(
        default=0, help_text="Upvotes from school admins (Vision Board)."
    )
    is_vip = models.BooleanField(
        default=False, help_text="VIP / high-priority feature request for roadmap."
    )

    class Meta:
        ordering = ["-is_vip", "-upvote_count", "-created_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["is_vip", "-upvote_count"]),
        ]

    def __str__(self):
        return f"{self.school.name}: {self.title} ({self.status})"


def get_feature_fragment_cap(school) -> int | None:
    if not school:
        return 0
    plan = getattr(school, "plan", None)
    if not plan:
        return 0
    slug = (getattr(plan, "slug", None) or "").strip().lower()
    caps = {"basic": 0, "pro": 2, "enterprise": 5}
    return caps.get(slug, 0)


class FeatureFragment(models.Model):
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
                    {
                        "__all__": [
                            f"Plan limit reached: this school can have at most {cap} custom fragment(s). Upgrade to add more."
                        ]
                    }
                )
        super().clean()
