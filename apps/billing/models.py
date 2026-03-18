from __future__ import annotations

from decimal import Decimal

from django.db import models


class BillingAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        TRIAL = "TRIAL", "Trial"
        PAST_DUE = "PAST_DUE", "Past due"
        SUSPENDED = "SUSPENDED", "Suspended"
        CANCELED = "CANCELED", "Canceled"

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="billing_account",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    billing_email = models.EmailField(blank=True)
    processor_code = models.CharField(max_length=32, blank=True, db_index=True)
    external_customer_ref = models.CharField(max_length=120, blank=True, db_index=True)
    currency_code = models.CharField(max_length=3, default="USD")
    last_processor_sync_at = models.DateTimeField(null=True, blank=True)
    delinquent_since = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school__name"]
        verbose_name = "Billing account"
        verbose_name_plural = "Billing accounts"

    def __str__(self):
        return f"{self.school.name} billing"


class TenantSubscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = "TRIALING", "Trialing"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        SUSPENDED = "SUSPENDED", "Suspended"
        CANCELED = "CANCELED", "Canceled"

    class BillingCycle(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        ANNUAL = "ANNUAL", "Annual"
        MANUAL = "MANUAL", "Manual"

    billing_account = models.ForeignKey(
        BillingAccount,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="platform_subscriptions",
    )
    plan = models.ForeignKey(
        "siteconfig.Plan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_subscriptions",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    billing_cycle = models.CharField(
        max_length=12, choices=BillingCycle.choices, default=BillingCycle.MONTHLY
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    external_subscription_ref = models.CharField(
        max_length=120, blank=True, db_index=True
    )
    last_invoiced_at = models.DateTimeField(null=True, blank=True)
    base_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    addons_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    billed_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    country_multiplier = models.DecimalField(
        max_digits=8, decimal_places=3, default=Decimal("1.000")
    )
    addon_codes = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "Tenant subscription"
        verbose_name_plural = "Tenant subscriptions"

    def __str__(self):
        return f"{self.school.name} subscription"


class UsageMeter(models.Model):
    billing_account = models.ForeignKey(
        BillingAccount,
        on_delete=models.CASCADE,
        related_name="usage_meters",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="platform_usage_meters",
    )
    metric_code = models.CharField(max_length=64, db_index=True)
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    quantity = models.PositiveBigIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start", "metric_code"]
        verbose_name = "Usage meter"
        verbose_name_plural = "Usage meters"
        constraints = [
            models.UniqueConstraint(
                fields=["billing_account", "metric_code", "period_start", "period_end"],
                name="billing_unique_usage_meter_period",
            )
        ]

    def __str__(self):
        return f"{self.school.name} {self.metric_code} {self.period_start:%Y-%m}"


class PlatformLedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        CHARGE = "CHARGE", "Charge"
        CREDIT = "CREDIT", "Credit"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        WRITE_OFF = "WRITE_OFF", "Write off"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOIDED = "VOIDED", "Voided"

    billing_account = models.ForeignKey(
        BillingAccount,
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="platform_ledger_entries",
    )
    entry_type = models.CharField(
        max_length=20, choices=EntryType.choices, db_index=True
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.POSTED, db_index=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency_code = models.CharField(max_length=3, default="USD")
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=120, blank=True, db_index=True)
    source = models.CharField(max_length=64, blank=True)
    source_ref = models.CharField(max_length=120, blank=True)
    happened_at = models.DateTimeField(db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-happened_at", "-created_at"]
        verbose_name = "Platform ledger entry"
        verbose_name_plural = "Platform ledger entries"

    def __str__(self):
        return f"{self.school.name} {self.entry_type} {self.amount}"


class BillingProcessorSyncEvent(models.Model):
    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        IGNORED = "IGNORED", "Ignored"
        FAILED = "FAILED", "Failed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_processor_events",
    )
    billing_account = models.ForeignKey(
        BillingAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processor_events",
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processor_events",
    )
    processor_code = models.CharField(max_length=32, db_index=True)
    event_type = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.APPLIED, db_index=True
    )
    external_customer_ref = models.CharField(max_length=120, blank=True, db_index=True)
    external_subscription_ref = models.CharField(
        max_length=120, blank=True, db_index=True
    )
    payload = models.JSONField(default=dict, blank=True)
    message = models.CharField(max_length=255, blank=True)
    happened_at = models.DateTimeField(db_index=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-happened_at", "-created_at"]
        verbose_name = "Billing processor sync event"
        verbose_name_plural = "Billing processor sync events"

    def __str__(self):
        return f"{self.processor_code} {self.event_type} {self.status}"


class PlatformBillingProcessorConfig(models.Model):
    class SignatureStyle(models.TextChoices):
        PLAIN_HMAC = "PLAIN_HMAC", "Plain HMAC"
        PREFIXED_HMAC = "PREFIXED_HMAC", "Prefixed HMAC"
        STRIPE_V1 = "STRIPE_V1", "Stripe v1"

    code = models.SlugField(max_length=32, unique=True)
    display_name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, db_index=True)
    signature_header = models.CharField(max_length=64, default="X-Signature")
    signature_algorithm = models.CharField(max_length=16, default="sha256")
    signature_style = models.CharField(
        max_length=24,
        choices=SignatureStyle.choices,
        default=SignatureStyle.PLAIN_HMAC,
    )
    webhook_secret = models.CharField(max_length=500, blank=True)
    timestamp_tolerance_seconds = models.PositiveIntegerField(default=300)
    event_allowlist = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_webhook_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Platform billing processor config"
        verbose_name_plural = "Platform billing processor configs"

    def __str__(self):
        return self.display_name or self.code


class RevenueSharePayout(models.Model):
    class Scope(models.TextChoices):
        APP_PUBLISHER = "APP_PUBLISHER", "App publisher"
        CHANNEL_PARTNER = "CHANNEL_PARTNER", "Channel partner"
        AFFILIATE = "AFFILIATE", "Affiliate"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SCHEDULED = "SCHEDULED", "Scheduled"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        VOIDED = "VOIDED", "Voided"

    source_school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revenue_share_payouts",
    )
    payout_scope = models.CharField(
        max_length=32, choices=Scope.choices, default=Scope.APP_PUBLISHER, db_index=True
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    payee_name = models.CharField(max_length=160)
    payee_ref = models.CharField(max_length=120, blank=True, db_index=True)
    processor_code = models.CharField(max_length=32, blank=True, db_index=True)
    external_payout_ref = models.CharField(max_length=120, blank=True, db_index=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    gross_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    fee_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    net_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    currency_code = models.CharField(max_length=3, default="USD")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Revenue share payout"
        verbose_name_plural = "Revenue share payouts"

    def __str__(self):
        return f"{self.payee_name} {self.net_amount}"


class Quote(models.Model):
    """
    Commercial platform (29.10): quote for plan/contract before subscription.
    Self-serve trials use School.trial_end_date; this model supports quote-to-contract flow.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        ACCEPTED = "ACCEPTED", "Accepted"
        EXPIRED = "EXPIRED", "Expired"
        DECLINED = "DECLINED", "Declined"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="quotes",
        null=True,
        blank=True,
    )
    plan = models.ForeignKey(
        "siteconfig.Plan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    currency_code = models.CharField(max_length=3, default="USD")
    valid_until = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Quote"
        verbose_name_plural = "Quotes"

    def __str__(self):
        return f"Quote #{self.id} {self.get_status_display()}"
