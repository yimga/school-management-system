"""
Multi-tenant School and SchoolMembership models (Option B+C).
School is the tenant; SchoolMembership links users to schools with a role.
Phase D: Plan + addons; is_feature_enabled(tenant, code) for feature gate.
"""
import uuid
from django.conf import settings
from django.db import models


def is_feature_enabled(school, code: str) -> bool:
    """
    Return True if the tenant (school) has the feature/module enabled.
    Phase D: (1) plan.included_features, (2) school.addons, (3) School.features + FeatureToggleState.
    Phase E: When billing_type is COMPLIMENTARY or MANUAL_OVERRIDE, grant full access (return True).
    """
    if school is None:
        return False
    # Phase E: Billing waiver — skip plan/feature checks and grant full access
    billing_type = getattr(school, "billing_type", None)
    if billing_type in ("COMPLIMENTARY", "MANUAL_OVERRIDE"):
        return True
    normalized = (code or "").strip().lower()
    if not normalized:
        return False
    plan = getattr(school, "plan", None)
    if plan and getattr(plan, "included_features", None):
        included = [str(x).strip().lower() for x in plan.included_features if x]
        if normalized in included:
            return True
    addons = getattr(school, "addons", None) or []
    if isinstance(addons, list):
        addon_set = [str(x).strip().lower() for x in addons if x]
        if normalized in addon_set:
            return True
    # Phase A: getTenantModules — union of feature keys from TenantSystem + SystemFeature
    try:
        from apps.siteconfig.tenant_config import get_tenant_modules
        if normalized in (get_tenant_modules(school) or []):
            return True
    except Exception:
        pass
    return _has_feature_fallback(school, code)


def _has_feature_fallback(school, code: str) -> bool:
    """Legacy: School.features + resolve_module_enabled."""
    normalized = (code or "").strip().lower()
    if not normalized:
        return False
    fallback = bool(school.features.get(normalized)) if isinstance(getattr(school, "features", None), dict) else False
    try:
        from apps.siteconfig.feature_toggles import resolve_module_enabled
        return resolve_module_enabled(normalized, school=school, fallback=fallback)
    except Exception:
        return fallback


def _get_role_choices():
    from apps.accounts.models import User
    return User.Role.choices


class School(models.Model):
    """Tenant: one row per school. Subdomain/slug identifies the school in the URL."""

    class SubSystem(models.TextChoices):
        FR = "FR", "French sub-system"
        EN = "EN", "English sub-system"
        INT = "INT", "International"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True, help_text="URL slug e.g. ghs-limbe")
    name = models.CharField(max_length=255)
    subdomain = models.CharField(
        max_length=120,
        unique=True,
        blank=True,
        help_text="Subdomain for this school (e.g. ghs-limbe for ghs-limbe.yoursystem.com)",
    )
    sub_system = models.CharField(
        max_length=10,
        choices=SubSystem.choices,
        default=SubSystem.EN,
        help_text="Cameroon FR/EN or International",
    )
    default_region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="schools",
        help_text="Region for currency, grading, timezone",
    )
    timezone = models.CharField(max_length=50, default="Africa/Douala")
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="School-level overrides: grading_logic, term_count, custom fields config, etc.",
    )
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Enabled modules: {\"library\": true, \"transport\": false}",
    )
    logo_url = models.URLField(blank=True, help_text="URL to school logo (e.g. from tenants/{id}/logo.png)")
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    is_active = models.BooleanField(default=True)
    # Phase 4: super-tenant (parent school for consolidated dashboard)
    parent_school = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_schools",
        help_text="Parent tenant e.g. Catholic Education Secretariat",
    )
    # Phase 4: whitelabel custom domain
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom domain e.g. portal.school.edu",
    )
    custom_domain_verified = models.BooleanField(default=False)
    # Phase B/H: Admin theme choice (Unfold [RECOMMENDED], Jazzmin, Sneat); optional "Change theme" in settings.
    theme_choice = models.CharField(
        max_length=20,
        choices=[
            ("UNFOLD", "Unfold (Modern)"),
            ("JAZZMIN", "Jazzmin (Classic)"),
            ("SNEAT", "Sneat (Enterprise)"),
        ],
        default="UNFOLD",
        blank=True,
        help_text="Admin/backend theme. Change theme in School edit or Site settings.",
    )
    plan = models.ForeignKey(
        "siteconfig.Plan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schools",
        help_text="Subscription plan; included_features + addons determine enabled modules.",
    )
    addons = models.JSONField(
        default=list,
        blank=True,
        help_text="Additional feature codes beyond plan (e.g. ['design_studio', 'inventory'])",
    )
    class BillingType(models.TextChoices):
        REGULAR = "REGULAR", "Regular (paying)"
        FREE_TRIAL = "FREE_TRIAL", "Free trial"
        COMPLIMENTARY = "COMPLIMENTARY", "Complimentary (waived)"
        MANUAL_OVERRIDE = "MANUAL_OVERRIDE", "Manual override (full access)"

    billing_type = models.CharField(
        max_length=20,
        choices=BillingType.choices,
        default=BillingType.REGULAR,
        help_text="When COMPLIMENTARY or MANUAL_OVERRIDE, billing checks are skipped; waiver_note required.",
    )
    waiver_note = models.TextField(
        blank=True,
        help_text="Required when billing_type is COMPLIMENTARY or MANUAL_OVERRIDE (e.g. partnership with NGO).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Phase H: Optional approval workflow; Super Admin can list/filter unapproved schools.
    is_approved = models.BooleanField(
        default=True,
        help_text="When False, school is pending approval. Default True for backward compatibility.",
    )
    last_activity = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Phase H optional: last request time for this tenant (throttled updates).",
    )
    # Section 8.7: Account freeze (storage/billing limit exceeded)
    is_frozen = models.BooleanField(
        default=False,
        help_text="When True, tenant is restricted (e.g. storage or billing); middleware redirects to frozen page except billing/logout.",
    )
    frozen_reason = models.CharField(
        max_length=30,
        blank=True,
        choices=[
            ("", "—"),
            ("STORAGE", "Storage limit exceeded"),
            ("BILLING", "Subscription overdue"),
        ],
        help_text="Reason for freeze; required when is_frozen is True.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name

    def has_feature(self, code: str) -> bool:
        """Return True if the school has the given feature/module enabled. Phase D: considers plan + addons."""
        return is_feature_enabled(self, code)

    def get_cname_target(self) -> str:
        """Return the hostname schools should CNAME their custom_domain to (whitelabel Phase 4)."""
        import os
        base = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip()
        return base or "your-platform.com"


class SchoolProvisioningEvent(models.Model):
    """Audit trail for school onboarding and domain-verification lifecycle."""

    class EventType(models.TextChoices):
        REQUEST_RECEIVED = "REQUEST_RECEIVED", "Request Received"
        QUEUED = "QUEUED", "Queued"
        STARTED = "STARTED", "Started"
        PROFILE_APPLIED = "PROFILE_APPLIED", "Profile Applied"
        ACADEMIC_YEAR_READY = "ACADEMIC_YEAR_READY", "Academic Year Ready"
        SUBJECTS_READY = "SUBJECTS_READY", "Subjects Ready"
        DOMAIN_PENDING = "DOMAIN_PENDING", "Domain Pending"
        DOMAIN_VERIFIED = "DOMAIN_VERIFIED", "Domain Verified"
        DOMAIN_UNVERIFIED = "DOMAIN_UNVERIFIED", "Domain Unverified"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    class Status(models.TextChoices):
        INFO = "INFO", "Info"
        SUCCESS = "SUCCESS", "Success"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="provisioning_events",
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INFO)
    message = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="school_provisioning_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["event_type"]),
        ]
        verbose_name = "School provisioning event"
        verbose_name_plural = "School provisioning events"

    def __str__(self):
        return f"{self.school.name}: {self.event_type} ({self.status})"

    @classmethod
    def log_event(
        cls,
        *,
        school: School | None,
        event_type: str,
        status: str = Status.INFO,
        message: str = "",
        payload: dict | None = None,
        created_by=None,
    ):
        if school is None:
            return None
        return cls.objects.create(
            school=school,
            event_type=event_type,
            status=status,
            message=message or "",
            payload=payload or {},
            created_by=created_by if getattr(created_by, "pk", None) else None,
        )


class SchoolMembership(models.Model):
    """Links a user to a school with a role. User can belong to multiple schools."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_memberships",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=_get_role_choices,
        default="ADMIN",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="When user has multiple schools, which one is primary",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "school")]
        ordering = ["-is_primary", "school__name"]
        verbose_name = "School membership"
        verbose_name_plural = "School memberships"

    def __str__(self):
        return f"{self.user.username} @ {self.school.name} ({self.role})"
