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
    wallpaper_url = models.URLField(
        blank=True,
        help_text="URL to tenant login wallpaper (split-screen left panel image)",
    )
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
    # Multi-level hierarchy: materialized path (e.g. "" or "uuid1" or "uuid1/uuid2") for recursive queries
    hierarchy_path = models.CharField(
        max_length=1024,
        blank=True,
        db_index=True,
        help_text="Slash-separated UUIDs from root to parent; empty for root. Used for get_descendants/get_ancestors.",
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
    # W3-5: Per-tenant theme pack (portal/login). When set, overrides global SiteSettings theme for this school.
    theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schools_using_theme",
        help_text="Portal/login theme pack for this school. Leave blank to use global default.",
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
    trial_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="When billing_type is FREE_TRIAL, trial ends on this date.",
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
    # Plan XXI: Compliance Region — GDPR (EU), FERPA (US), NDPR (Nigeria). Enables data masking, retention, consent flows.
    class ComplianceRegion(models.TextChoices):
        NONE = "", "None (default)"
        EU = "EU", "EU (GDPR)"
        US = "US", "US (FERPA)"
        NDPR = "NDPR", "Nigeria (NDPR)"

    compliance_region = models.CharField(
        max_length=10,
        choices=ComplianceRegion.choices,
        default=ComplianceRegion.NONE,
        blank=True,
        help_text="Compliance region for data privacy: EU (GDPR), US (FERPA), Nigeria (NDPR). Affects masking, retention, consent.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Keep materialized path in sync for multi-level hierarchy
        if self.parent_school_id:
            parent = School.objects.filter(pk=self.parent_school_id).first()
            if parent:
                base = (getattr(parent, "hierarchy_path", "") or "").strip()
                self.hierarchy_path = (base + "/" + str(parent.pk)).strip("/") if base else str(parent.pk)
            else:
                self.hierarchy_path = str(self.parent_school_id)
        else:
            self.hierarchy_path = ""
        super().save(*args, **kwargs)

    def has_feature(self, code: str) -> bool:
        """Return True if the school has the given feature/module enabled. Phase D: considers plan + addons."""
        return is_feature_enabled(self, code)

    def get_cname_target(self) -> str:
        """Return the hostname schools should CNAME their custom_domain to (whitelabel Phase 4)."""
        import os
        base = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip()
        return base or "your-platform.com"

    def get_ancestor_chain(self) -> list:
        """
        Return list of parent schools from this school up to root (for deeper nested tenancy).
        Order: [immediate_parent, grandparent, ...]. Empty if no parent.
        """
        chain = []
        current = self.parent_school
        seen = {self.pk}
        while current and current.pk not in seen:
            seen.add(current.pk)
            chain.append(current)
            current = getattr(current, "parent_school", None)
        return chain

    def get_root_school(self) -> "School | None":
        """Return the top-level parent in the tenant hierarchy, or self if no parent."""
        chain = self.get_ancestor_chain()
        return chain[-1] if chain else (None if self.parent_school_id else self)

    def get_descendants(self, include_self=False):
        """Return all schools in the subtree (children, grandchildren, ...). Uses hierarchy_path when set."""
        from django.db.models import Q
        # Path format: root has ""; child has "/root_id"; grandchild has "/root_id/parent_id"
        if self.hierarchy_path:
            prefix = (self.hierarchy_path + "/" + str(self.pk)).strip("/")
            qs = School.objects.filter(
                Q(hierarchy_path=prefix) | Q(hierarchy_path__startswith=prefix + "/"),
                is_active=True,
            )
        else:
            qs = School.objects.filter(parent_school_id=self.pk, is_active=True)
        if include_self:
            qs = School.objects.filter(Q(pk=self.pk) | Q(pk__in=qs.values_list("id", flat=True)), is_active=True)
        return qs

    def get_ancestors(self):
        """Return all ancestor schools (parent, grandparent, ...) using hierarchy_path or parent_school walk."""
        if self.hierarchy_path:
            uuids = [u.strip() for u in self.hierarchy_path.split("/") if u.strip()]
            if not uuids:
                return School.objects.none()
            return School.objects.filter(pk__in=uuids, is_active=True)
        return type(self).objects.filter(pk__in=[p.pk for p in self.get_ancestor_chain()])


class Campus(models.Model):
    """
    Multi-campus: physical site under one School. Optional; use when a school has
    multiple locations (e.g. Main Campus, North Campus). Student/classroom can link to campus.
    """
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="campuses",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32, blank=True, help_text="Short code e.g. MAIN, NORTH")
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "name"]
        verbose_name = "Campus"
        verbose_name_plural = "Campuses"

    def __str__(self):
        return f"{self.name} ({self.school.name})"


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


class SchoolDomain(models.Model):
    """
    Multiple domains per tenant (shared schema). Used for subdomain and custom domains;
    Caddy ask endpoint and middleware resolve tenant from domain. DNS verification
    uses dns_token (TXT runyourcampus-verify=<token>).
    """

    class Kind(models.TextChoices):
        SUBDOMAIN = "SUBDOMAIN", "Subdomain"
        CUSTOM = "CUSTOM", "Custom domain"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="domain_entries",
    )
    domain = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Hostname e.g. school.runyourcampus.com or portal.school.edu",
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="True after TXT verification (custom) or when created from School.subdomain (subdomain).",
    )
    dns_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="TXT record runyourcampus-verify=<token> for custom domain verification.",
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.CUSTOM,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["school", "domain"]
        unique_together = [("school", "domain")]
        indexes = [
            models.Index(fields=["domain"]),
            models.Index(fields=["is_verified", "domain"]),
        ]
        verbose_name = "School domain"
        verbose_name_plural = "School domains"

    def __str__(self):
        return f"{self.domain} → {self.school.name}"


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


class SignupVerification(models.Model):
    """
    Token for self-service school signup email verification. School is created
    with is_active=False; when user clicks link with valid token, school is
    activated and provisioning runs.
    """
    school = models.OneToOneField(
        School,
        on_delete=models.CASCADE,
        related_name="signup_verification",
    )
    email = models.EmailField()
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Signup verification"
        verbose_name_plural = "Signup verifications"

    def __str__(self):
        return f"{self.email} → {self.school.name}"


class TenantQuotaLimit(models.Model):
    """Per-tenant API/quota limits for SaaS billing and fairness (Plan I)."""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="quota_limits",
    )
    limit_type = models.CharField(
        max_length=64,
        help_text="e.g. api_calls_per_month, api_calls_per_minute, storage_mb",
    )
    limit_value = models.PositiveIntegerField(help_text="Numeric limit")
    period_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Period length in days (e.g. 30 for monthly); null for per-minute.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "limit_type"]
        unique_together = [("school", "limit_type")]
        verbose_name = "Tenant quota limit"
        verbose_name_plural = "Tenant quota limits"

    def __str__(self):
        return f"{self.school.name}: {self.limit_type}={self.limit_value}"


class TenantApiUsage(models.Model):
    """Per-tenant API usage for billing and super-admin dashboard (Plan I)."""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="api_usage_records",
    )
    period_date = models.DateField(help_text="Date (or first day of period) for aggregation")
    request_count = models.PositiveIntegerField(default=0)
    limit_type = models.CharField(
        max_length=64,
        default="api_calls",
        help_text="Matches TenantQuotaLimit.limit_type",
    )

    class Meta:
        ordering = ["-period_date", "school"]
        unique_together = [("school", "period_date", "limit_type")]
        verbose_name = "Tenant API usage"
        verbose_name_plural = "Tenant API usage"

    def __str__(self):
        return f"{self.school.name} {self.period_date}: {self.request_count}"


# Plan XVI: Inventory / assets
class InventoryItem(models.Model):
    """School inventory/asset item (e.g. lab equipment, books)."""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="inventory_items",
    )
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Inventory item"
        verbose_name_plural = "Inventory items"

    def __str__(self):
        return f"{self.name} ({self.quantity})"


# Plan XVI: Transport — routes, stops, buses
class Route(models.Model):
    """Transport route (e.g. Morning North)."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="transport_routes")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("school", "name")]

    def __str__(self):
        return self.name


class Stop(models.Model):
    """Stop on a route."""
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    name = models.CharField(max_length=120)
    sequence = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["route", "sequence"]
        unique_together = [("route", "sequence")]

    def __str__(self):
        return f"{self.route.name}: {self.name}"


class Bus(models.Model):
    """Bus/vehicle; optional assignment to route."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="buses")
    identifier = models.CharField(max_length=60, help_text="e.g. Bus 01, Plate number")
    route = models.ForeignKey(
        Route,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buses",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["identifier"]
        unique_together = [("school", "identifier")]

    def __str__(self):
        return self.identifier
