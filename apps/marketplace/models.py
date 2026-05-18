"""
Marketplace MVP: installable apps, scopes, widget registry, audit (RunMyCampus blueprint).
Control-plane models (shared schema); install pipeline records install + registers widgets/scopes.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

# School is the tenant in both RLS and schema-per-tenant (via bridge).
# Use string ref to avoid circular import; schools.School.id is UUID.
AUTH_USER_MODEL = getattr(settings, "AUTH_USER_MODEL", "accounts.User")


class PublisherOrganization(models.Model):
    """Verified publisher/developer organization for the governed marketplace."""

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        PENDING = "pending", "Pending review"
        VERIFIED = "verified", "Verified"
        SUSPENDED = "suspended", "Suspended"

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True,
    )
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    verified_contact_email = models.EmailField(
        blank=True,
        db_index=True,
        help_text="Operator/owner email used to link platform user accounts to this publisher.",
    )
    website_url = models.URLField(max_length=500, blank=True)
    support_email = models.EmailField(blank=True)
    payout_email = models.EmailField(blank=True)
    payout_processor_code = models.CharField(max_length=32, blank=True)
    payout_ref = models.CharField(max_length=120, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Publisher organization"
        verbose_name_plural = "Publisher organizations"
        ordering = ["name"]

    def __str__(self):
        return self.name


class MarketplaceApp(models.Model):
    """
    Catalog entry for an installable app (first-party or later third-party).
    Manifest: scopes, UI widgets, migrations_ref, events consumed/emitted.
    """

    class AppKind(models.TextChoices):
        FIRST_PARTY = "first_party", "First-party"
        THIRD_PARTY = "third_party", "Third-party"
        PREMIUM = "premium", "Premium"
        TENANT_PRIVATE = "tenant_private", "Tenant-private"
        CONNECTOR = "connector", "Connector"

    publisher = models.ForeignKey(
        PublisherOrganization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="apps",
    )
    slug = models.SlugField(max_length=80, unique=True)
    app_key = models.CharField(
        max_length=80,
        unique=True,
        db_index=True,
        help_text="Stable developer-platform app id (defaults to slug).",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    kind = models.CharField(
        max_length=20, choices=AppKind.choices, default=AppKind.FIRST_PARTY
    )
    version = models.CharField(max_length=32)
    required_apps = models.JSONField(
        default=list,
        blank=True,
        help_text="app_key values that must be installed first (dependencies).",
    )
    webhook_subscriptions = models.JSONField(
        default=list,
        blank=True,
        help_text="Declared webhook topics / filters for governance and delivery.",
    )
    install_hooks = models.JSONField(
        default=list,
        blank=True,
        help_text="HTTPS URLs or internal hook keys invoked after install.",
    )
    uninstall_hooks = models.JSONField(
        default=list,
        blank=True,
        help_text="HTTPS URLs or internal hook keys invoked on uninstall.",
    )
    # Manifest: required scopes, widget definitions, optional migration_ref / webhook subscriptions
    manifest = models.JSONField(
        default=dict,
        help_text="scopes, widgets, events_consumed, events_emitted, migration_ref",
    )
    class PricingModel(models.TextChoices):
        FREE = "free", "Free"
        SUBSCRIPTION = "subscription", "Subscription"
        USAGE = "usage", "Usage"

    class BillingInterval(models.TextChoices):
        NONE = "none", "Not applicable"
        MONTHLY = "monthly", "Monthly"
        ANNUAL = "annual", "Annual"

    # Commercial catalog hooks (monetization architecture)
    pricing_model = models.CharField(
        max_length=20,
        choices=PricingModel.choices,
        default=PricingModel.FREE,
        db_index=True,
    )
    is_intentionally_free = models.BooleanField(
        default=False,
        db_index=True,
        help_text="When pricing is Free, check this to confirm a deliberate $0 catalog offer (not a missing price).",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="List price in the tenant billing account currency (subscription or usage floor).",
    )
    billing_interval = models.CharField(
        max_length=16,
        choices=BillingInterval.choices,
        default=BillingInterval.NONE,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Marketplace App"
        verbose_name_plural = "Marketplace Apps"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.pricing_model == self.PricingModel.FREE and not self.is_intentionally_free:
            raise ValidationError(
                {
                    "is_intentionally_free": "Confirm this is an intentional free listing, or set a paid pricing model."
                }
            )

    def save(self, *args, **kwargs):
        if not self.app_key:
            self.app_key = self.slug
        if not kwargs.get("raw", False) and (
            self.pricing_model == self.PricingModel.FREE and not self.is_intentionally_free
        ):
            self.full_clean()
        super().save(*args, **kwargs)


class AppPermissionScope(models.Model):
    """
    Platform catalog entry for a permission string (maps to AppScope.scope_code and OAuth scopes).
    """

    class Access(models.TextChoices):
        READ = "read", "Read"
        WRITE = "write", "Write"
        ADMIN = "admin", "Admin"

    code = models.CharField(max_length=80, unique=True, db_index=True)
    domain = models.CharField(
        max_length=64,
        blank=True,
        help_text="Logical domain, e.g. students, finance, marketplace.",
    )
    access = models.CharField(
        max_length=8,
        choices=Access.choices,
        default=Access.READ,
    )
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "App permission scope"
        verbose_name_plural = "App permission scopes"
        ordering = ["domain", "code"]

    def __str__(self):
        return self.code


class MarketplaceListing(models.Model):
    """Control-plane listing state for app review, certification, and revenue share."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_REVIEW = "pending_review", "Pending review"
        APPROVED = "approved", "Approved"
        SUSPENDED = "suspended", "Suspended"
        REJECTED = "rejected", "Rejected"

    class ReviewStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        CHANGES_REQUIRED = "changes_required", "Changes required"
        REJECTED = "rejected", "Rejected"

    app = models.OneToOneField(
        MarketplaceApp,
        on_delete=models.CASCADE,
        related_name="listing",
    )
    publisher = models.ForeignKey(
        PublisherOrganization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listings",
    )
    category = models.CharField(max_length=80, blank=True)
    short_description = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    security_review_status = models.CharField(
        max_length=24,
        choices=ReviewStatus.choices,
        default=ReviewStatus.NOT_REQUIRED,
        db_index=True,
    )
    certification_status = models.CharField(
        max_length=24,
        choices=ReviewStatus.choices,
        default=ReviewStatus.NOT_REQUIRED,
        db_index=True,
    )
    revenue_share_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    kill_switch_active = models.BooleanField(default=False, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)
    compatibility = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional: countries (list), blueprint_families (list), plan_tiers (list), workflow_families (list), recommended_sectors (list of wedge 14–22 sector codes e.g. PUBLIC, NGO).",
    )
    # GAP.11 / III.23: preview and screenshots for catalog UI
    preview_image_url = models.URLField(
        max_length=500, blank=True, help_text="Main preview/hero image URL for catalog."
    )
    screenshot_urls = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional list of screenshot image URLs for app listing.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Marketplace listing"
        verbose_name_plural = "Marketplace listings"
        ordering = ["app__name"]

    def __str__(self):
        return f"{self.app.name} listing"

    def save(self, *args, **kwargs):
        if self.publisher_id is None and getattr(self.app, "publisher_id", None):
            self.publisher_id = self.app.publisher_id
        super().save(*args, **kwargs)

    @property
    def installable(self) -> bool:
        if self.kill_switch_active:
            return False
        if self.status != self.Status.APPROVED:
            return False
        if self.app.kind == MarketplaceApp.AppKind.THIRD_PARTY:
            return self.security_review_status == self.ReviewStatus.APPROVED
        return True


class MarketplaceReview(models.Model):
    """Queue item for listing, security, certification, and version review."""

    class ReviewType(models.TextChoices):
        LISTING = "listing", "Listing review"
        SECURITY = "security", "Security review"
        CERTIFICATION = "certification", "Certification review"
        VERSION = "version", "Version review"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_REVIEW = "in_review", "In review"
        APPROVED = "approved", "Approved"
        CHANGES_REQUIRED = "changes_required", "Changes required"
        REJECTED = "rejected", "Rejected"

    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    review_type = models.CharField(
        max_length=24, choices=ReviewType.choices, db_index=True
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    requested_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    app_version = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)
    findings_json = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Marketplace review"
        verbose_name_plural = "Marketplace reviews"
        ordering = ["status", "-requested_at"]

    def __str__(self):
        return f"{self.listing.app.slug} {self.review_type} {self.status}"

    def mark_reviewed(
        self, *, status: str, reviewed_by=None, notes: str = "", findings_json=None
    ):
        self.status = status
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        if notes:
            self.notes = notes
        if findings_json is not None:
            self.findings_json = findings_json
        self.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "notes",
                "findings_json",
                "updated_at",
            ]
        )


class AppScope(models.Model):
    """Permission scope declared by an app (OAuth-style least privilege)."""

    app = models.ForeignKey(
        MarketplaceApp, on_delete=models.CASCADE, related_name="scopes"
    )
    permission_scope = models.ForeignKey(
        AppPermissionScope,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="app_scope_links",
        help_text="Optional link to the canonical platform scope definition.",
    )
    scope_code = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    sensitive = models.BooleanField(
        default=False,
        help_text="If True, scope requires elevated approval before grant.",
    )

    class Meta:
        app_label = "marketplace"
        unique_together = [["app", "scope_code"]]
        verbose_name = "App Scope"
        verbose_name_plural = "App Scopes"
        ordering = ["app", "scope_code"]

    def __str__(self):
        return f"{self.app.slug}:{self.scope_code}"


class AppInstallation(models.Model):
    """Tenant (school) has installed an app; tracks config and status."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        UNINSTALLED = "uninstalled", "Uninstalled"

    class InstallPhase(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox (pre-activation)"
        ACTIVE = "active", "Active"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="app_installations",
    )
    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.PROTECT,
        related_name="installations",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    install_phase = models.CharField(
        max_length=20,
        choices=InstallPhase.choices,
        default=InstallPhase.ACTIVE,
        db_index=True,
        help_text="Sandbox = pre-activation; Active = fully active.",
    )
    last_health_at = models.DateTimeField(null=True, blank=True)
    health_status = models.CharField(max_length=32, blank=True, db_index=True)
    uninstalled_at = models.DateTimeField(null=True, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    installed_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    config = models.JSONField(default=dict, help_text="Tenant-specific app config")
    # Resolved widget list for this tenant (from app.manifest + overrides)
    widget_config = models.JSONField(default=dict, blank=True)
    installed_version = models.CharField(
        max_length=32,
        blank=True,
        help_text="Semver of the app payload active for this tenant (upgrade / rollback).",
    )

    class Meta:
        app_label = "marketplace"
        unique_together = [["school", "app"]]
        verbose_name = "App Installation"
        verbose_name_plural = "App Installations"
        ordering = ["-installed_at"]
        indexes = [
            models.Index(fields=["school", "status"], name="mkt_inst_school_status"),
        ]

    def __str__(self):
        return f"{self.app.slug} @ {self.school.slug}"


class ScopeGrant(models.Model):
    """
    Tenant-approved scope for an installation: which permissions this app has at this school.
    Tenant admin must approve; least-privilege (RunMyCampus blueprint).
    Sensitive scopes use status=pending until elevated_approved_by is set.
    """

    class GrantStatus(models.TextChoices):
        PENDING = "pending", "Pending approval"
        GRANTED = "granted", "Granted"

    installation = models.ForeignKey(
        AppInstallation,
        on_delete=models.CASCADE,
        related_name="scope_grants",
    )
    scope = models.ForeignKey(
        AppScope,
        on_delete=models.CASCADE,
        related_name="grants",
    )
    status = models.CharField(
        max_length=16,
        choices=GrantStatus.choices,
        default=GrantStatus.GRANTED,
        db_index=True,
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    elevated_approved_at = models.DateTimeField(null=True, blank=True)
    elevated_approved_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_scope_grant_elevated_set",
    )

    class Meta:
        app_label = "marketplace"
        unique_together = [["installation", "scope"]]
        verbose_name = "Scope Grant"
        verbose_name_plural = "Scope Grants"
        ordering = ["installation", "scope"]

    def __str__(self):
        return f"{self.installation} ← {self.scope}"


class AppBillingLedger(models.Model):
    """
    Billing line items for marketplace apps: install fee, subscription, proration (RunMyCampus blueprint).
    """

    class Kind(models.TextChoices):
        INSTALL_FEE = "install_fee", "Install fee"
        SUBSCRIPTION = "subscription", "Subscription"
        PRORATION_CREDIT = "proration_credit", "Proration credit"
        PRORATION_DEBIT = "proration_debit", "Proration debit"
        USAGE = "usage", "Usage"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="app_billing_ledger",
    )
    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.PROTECT,
        related_name="billing_ledger",
    )
    installation = models.ForeignKey(
        AppInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_ledger",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "App Billing Ledger"
        verbose_name_plural = "App Billing Ledger"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.app.slug} {self.kind} {self.amount} {self.currency}"


class TenantMarketplaceSubscription(models.Model):
    """
    Billable subscription row for a tenant app installation (add-on to core platform billing).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"

    installation = models.OneToOneField(
        AppInstallation,
        on_delete=models.CASCADE,
        related_name="marketplace_subscription",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="marketplace_app_subscriptions",
    )
    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.PROTECT,
        related_name="tenant_subscriptions",
    )
    billing_account = models.ForeignKey(
        "billing.BillingAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_app_subscriptions",
    )
    pricing_model = models.CharField(max_length=20, db_index=True)
    unit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    billing_interval = models.CharField(max_length=16, default="none")
    currency_code = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Tenant marketplace subscription"
        verbose_name_plural = "Tenant marketplace subscriptions"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.school_id} {self.app.slug} ({self.status})"


class PlatformMarketplaceEarning(models.Model):
    """Logged revenue split for marketplace charges (platform fee vs publisher pool)."""

    class Source(models.TextChoices):
        INSTALL = "install", "Install / activation"
        USAGE = "usage", "Usage billing"
        PAYMENT = "payment", "Payment processor settlement"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="marketplace_platform_earnings",
    )
    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_earnings",
    )
    installation = models.ForeignKey(
        AppInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_earnings",
    )
    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_earnings",
    )
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.INSTALL)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    platform_fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    publisher_pool_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Gross minus platform fee (remainder before publisher revenue-share).",
    )
    publisher_share_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Amount accruing to the listing publisher per revenue_share_percent.",
    )
    currency_code = models.CharField(max_length=3, default="USD")
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Platform marketplace earning"
        verbose_name_plural = "Platform marketplace earnings"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.gross_amount} {self.currency_code} ({self.source})"


class AppAuditLog(models.Model):
    """Audit trail for install/uninstall and scope grants."""

    installation = models.ForeignKey(
        AppInstallation,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="marketplace_audit_logs",
    )
    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict)
    actor = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "App Audit Log"
        verbose_name_plural = "App Audit Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} @ {self.created_at}"


class MarketplaceMonetizationLedgerEntry(models.Model):
    """Tenant-scoped marketplace monetization ledger (migration 0011 — metering parity)."""

    class EventType(models.TextChoices):
        INSTALL = "install", "Install"
        UNINSTALL = "uninstall", "Uninstall"
        SUBSCRIPTION_STARTED = "subscription_started", "Subscription started"
        USAGE_RECORDED = "usage_recorded", "Usage recorded"
        INVOICE_CREATED = "invoice_created", "Invoice created"
        PAYMENT_SUCCESS = "payment_success", "Payment success"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        PLATFORM_FEE_RECORDED = "platform_fee_recorded", "Platform fee recorded"
        SETTLEMENT_PENDING = "settlement_pending", "Settlement pending"
        SETTLEMENT_READY = "settlement_ready", "Settlement ready (awaiting PSP payout)"
        SETTLEMENT_COMPLETED = "settlement_completed", "Settlement completed"
        SETTLEMENT_FAILED = "settlement_failed", "Settlement failed"
        SETTLEMENT_RECONCILED = "settlement_reconciled", "Settlement reconciled (manual)"
        SETTLEMENT_EXTERNAL_BLOCKED = (
            "settlement_external_blocked",
            "Settlement blocked (external)",
        )
        SETTLEMENT_PENDING_EXTERNAL = (
            "settlement_pending_external",
            "Settlement pending (external PSP)",
        )

    class EntryStatus(models.TextChoices):
        POSTED = "posted", "Posted"
        PENDING = "pending", "Pending"
        FAILED = "failed", "Failed"
        BLOCKED = "blocked", "Blocked"

    class SettlementDependency(models.TextChoices):
        INTERNAL = "internal", "Internal metering"
        EXTERNAL_PSP = "external_psp", "External PSP"
        MANUAL = "manual", "Manual / offline"

    sku_key = models.CharField(max_length=80, db_index=True, default="")
    event_type = models.CharField(
        max_length=40,
        db_index=True,
        choices=EventType.choices,
    )
    quantity = models.BigIntegerField(default=1)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    platform_fee_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    provider_reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16,
        db_index=True,
        choices=EntryStatus.choices,
        default=EntryStatus.POSTED,
    )
    settlement_dependency = models.CharField(
        max_length=20,
        db_index=True,
        choices=SettlementDependency.choices,
        default=SettlementDependency.EXTERNAL_PSP,
    )
    idempotency_key = models.CharField(max_length=190, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="monetization_ledger_entries",
    )
    installation = models.ForeignKey(
        "marketplace.AppInstallation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="monetization_ledger_entries",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="marketplace_monetization_ledger",
    )

    class Meta:
        app_label = "marketplace"
        verbose_name = "Marketplace monetization ledger entry"
        verbose_name_plural = "Marketplace monetization ledger entries"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "idempotency_key"],
                name="marketplace_mon_led_unique_school_idempotency",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.school_id})"


class AppVersionCompat(models.Model):
    """Version compatibility matrix (platform min version, app min/max)."""

    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.CASCADE,
        related_name="version_compat",
    )
    platform_min_version = models.CharField(max_length=32, blank=True)
    app_version_min = models.CharField(max_length=32, blank=True)
    app_version_max = models.CharField(max_length=32, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "App Version Compatibility"
        verbose_name_plural = "App Version Compatibility"

    def __str__(self):
        return f"{self.app.slug} {self.app_version_min or '*'}->{self.app_version_max or '*'}"


class AppVersion(models.Model):
    """Published semver release of a MarketplaceApp.

    The single `MarketplaceApp.version` field captures the currently-published
    version; this table captures the full history so tenants can pin, roll back,
    and upgrade between specific versions (Salesforce/Shopify parity).
    """

    class Channel(models.TextChoices):
        STABLE = "stable", "Stable"
        BETA = "beta", "Beta"
        ALPHA = "alpha", "Alpha"
        DEPRECATED = "deprecated", "Deprecated"

    app = models.ForeignKey(
        MarketplaceApp, on_delete=models.CASCADE, related_name="versions"
    )
    version = models.CharField(
        max_length=32,
        db_index=True,
        help_text="Semantic version, e.g. 1.4.2 or 2.0.0-beta.1.",
    )
    channel = models.CharField(
        max_length=16, choices=Channel.choices, default=Channel.STABLE, db_index=True
    )
    manifest_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Frozen copy of the app manifest at the moment this version was published.",
    )
    changelog = models.TextField(
        blank=True,
        help_text="Markdown release notes for this version.",
    )
    migration_ref = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional schema migration id required to run this version.",
    )
    is_published = models.BooleanField(default=False, db_index=True)
    is_yanked = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this version was yanked post-publish (security/bug).",
    )
    yanked_reason = models.CharField(max_length=255, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "App version"
        verbose_name_plural = "App versions"
        unique_together = [["app", "version"]]
        ordering = ["app", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["app", "channel", "is_published"], name="mkt_ver_app_ch_pub_idx"),
        ]

    def __str__(self):
        return f"{self.app.slug}@{self.version}"


class AppRating(models.Model):
    """Tenant-submitted rating + review for a MarketplaceApp.

    One rating per (school, app). Only tenants with an AppInstallation may rate
    (verified_install=True); operators may post unverified reviews flagged as such.
    """

    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        HIDDEN = "hidden", "Hidden"
        FLAGGED = "flagged", "Flagged"

    app = models.ForeignKey(
        MarketplaceApp, on_delete=models.CASCADE, related_name="ratings"
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="marketplace_app_ratings",
    )
    author = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    stars = models.PositiveSmallIntegerField(db_index=True)
    headline = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True)
    verified_install = models.BooleanField(default=False, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PUBLISHED,
        db_index=True,
    )
    publisher_reply = models.TextField(blank=True)
    publisher_replied_at = models.DateTimeField(null=True, blank=True)
    helpful_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "App rating"
        verbose_name_plural = "App ratings"
        unique_together = [["app", "school"]]
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(stars__gte=1) & models.Q(stars__lte=5),
                name="mkt_rating_stars_1_5",
            ),
        ]

    def __str__(self):
        return f"{self.app.slug} {self.stars}★ by {self.school_id}"


class WebhookEndpoint(models.Model):
    """Publisher-declared webhook endpoint for a MarketplaceApp.

    The platform delivers events (install, uninstall, scope_granted, etc.) to
    this URL signed with `secret`. WebhookDelivery rows track every attempt and
    surface delivery health in the partner dashboard.
    """

    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.CASCADE,
        related_name="webhook_endpoints",
    )
    url = models.URLField(max_length=500)
    description = models.CharField(max_length=255, blank=True)
    secret = models.CharField(
        max_length=128,
        help_text="HMAC-SHA256 secret; sent as X-RMC-Signature header.",
    )
    topics = models.JSONField(
        default=list,
        blank=True,
        help_text="Subscribed event topics, e.g. ['install', 'uninstall', 'scope_granted'].",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Webhook endpoint"
        verbose_name_plural = "Webhook endpoints"
        ordering = ["app", "-created_at"]

    def __str__(self):
        return f"{self.app.slug} → {self.url}"


class WebhookDelivery(models.Model):
    """Single delivery attempt of an event to a WebhookEndpoint.

    Status machine: pending → in_flight → succeeded | failed | abandoned.
    Failed rows are retried with exponential backoff up to max_attempts.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_FLIGHT = "in_flight", "In flight"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed (will retry)"
        ABANDONED = "abandoned", "Abandoned (max attempts)"

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    app = models.ForeignKey(
        MarketplaceApp,
        on_delete=models.CASCADE,
        related_name="webhook_deliveries",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_webhook_deliveries",
        help_text="Originating tenant, if event was tenant-scoped.",
    )
    topic = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict)
    signature = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=190, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=6)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    response_status_code = models.IntegerField(null=True, blank=True)
    response_body_snippet = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Webhook delivery"
        verbose_name_plural = "Webhook deliveries"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "idempotency_key"],
                name="mkt_webhook_delivery_unique_endpoint_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="mkt_wh_dlv_status_next_idx"),
        ]

    def __str__(self):
        return f"{self.endpoint_id} {self.topic} {self.status}"


class PublisherSignupRequest(models.Model):
    """Self-serve publisher registration request awaiting RMC operator review.

    Anyone can submit this form; on submit we send an email-verify token to
    `contact_email`. After verification an operator approves → a
    PublisherOrganization is created and linked to the requester's user.
    """

    class Status(models.TextChoices):
        EMAIL_PENDING = "email_pending", "Email verification pending"
        EMAIL_VERIFIED = "email_verified", "Email verified, awaiting review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    organization_name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    website_url = models.URLField(max_length=500, blank=True)
    contact_email = models.EmailField(db_index=True)
    contact_name = models.CharField(max_length=120, blank=True)
    intent = models.TextField(
        blank=True,
        help_text="Why the applicant wants to publish; what they intend to build.",
    )
    email_verify_token = models.CharField(
        max_length=64,
        unique=True,
        help_text="One-time token sent to contact_email.",
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.EMAIL_PENDING,
        db_index=True,
    )
    reviewer = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewer_notes = models.TextField(blank=True)
    publisher = models.ForeignKey(
        PublisherOrganization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signup_requests",
        help_text="Created PublisherOrganization once the request is approved.",
    )
    submitted_by = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Authenticated user who submitted, if any.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Publisher signup request"
        verbose_name_plural = "Publisher signup requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.organization_name} ({self.status})"


class CapabilityRegistry(models.Model):
    """
    Central registry of app capability codes (dashboard_widget, workflow_action, etc.).
    Apps declare these in manifest; platform uses this for compatibility and governance.
    """

    class Category(models.TextChoices):
        DASHBOARD_WIDGET = "dashboard_widget", "Dashboard widget"
        WORKFLOW_ACTION = "workflow_action", "Workflow action"
        WORKFLOW_CONDITION = "workflow_condition", "Workflow condition"
        INTEGRATION_ADAPTER = "integration_adapter", "Integration adapter"

    code = models.CharField(max_length=80, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=32, choices=Category.choices, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    compatibility_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional: required_roles, supported_pages, etc.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"
        verbose_name = "Capability (registry)"
        verbose_name_plural = "Capabilities (registry)"
        ordering = ["category", "code"]

    def __str__(self):
        return f"{self.code} ({self.get_category_display()})"
