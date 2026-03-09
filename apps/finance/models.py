from decimal import Decimal
from datetime import datetime, timedelta
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.people.models import StudentProfile, StudentGuardian
from apps.accounts.validators import (
    validate_document_file,
    validate_file_size_5mb,
    validate_receipt_file,
    validate_file_size_2mb
)
from apps.siteconfig.models import _tenant_upload_to


def _default_currency():
    """Platform default currency (no hardcoded XAF). See config.PLATFORM_DEFAULT_CURRENCY."""
    return getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD")


def _invoice_attachment_upload_to(instance, filename):
    """Tenant-scoped path for Invoice attachments (Section 25.3, media_tenant_scope.md)."""
    return _tenant_upload_to("finance/invoices")(instance, filename)


def _invoice_payment_proof_upload_to(instance, filename):
    """Tenant-scoped path for Invoice payment proofs (Section 25.3, media_tenant_scope.md)."""
    return _tenant_upload_to("finance/payment_proofs")(instance, filename)


class ComplianceProfile(models.Model):
    """
    Finance/payroll compliance and regional settings.
    currency_code and timezone drive display and reporting (e.g. trial balance, payment dates).
    SiteSettings can link one profile via compliance_profile for invoice/payment flows.
    """
    class ChartTemplate(models.TextChoices):
        OHADA = "OHADA", "OHADA"
        GENERIC = "GENERIC", "Generic"

    name = models.CharField(max_length=120)
    country_code = models.CharField(max_length=2)
    currency_code = models.CharField(max_length=3, default=_default_currency)
    currency_symbol = models.CharField(max_length=8, default=_default_currency)
    timezone = models.CharField(max_length=64, default=settings.TIME_ZONE)
    chart_template = models.CharField(max_length=20, choices=ChartTemplate.choices, default=ChartTemplate.GENERIC)
    # Phase 3: Global Flexibility – configure allowed payment methods per region/profile
    available_payment_methods = models.JSONField(
        default=list,
        help_text=(
            "List of allowed payment method codes (e.g., MTN_MOMO, ORANGE_MOMO, BANK, CASH). "
            "Defaults applied at migration time."
        ),
    )

    # Plan IV: VAT/GST by location; report in different currency (e.g. invoice in USD, report in AED)
    vat_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="VAT/GST rate as percentage (e.g. 19.25 for 19.25%%). Applied by location.",
    )
    report_currency_code = models.CharField(
        max_length=3,
        blank=True,
        default="",
        help_text="When set, reports show amounts in this currency (e.g. AED). Leave blank to use currency_code.",
    )

    min_wage = models.DecimalField(max_digits=12, decimal_places=2, default=60000)
    default_hours_per_week = models.DecimalField(max_digits=6, decimal_places=2, default=40)
    overtime_multiplier = models.DecimalField(max_digits=6, decimal_places=2, default=1.5)
    annual_leave_days = models.PositiveSmallIntegerField(default=21)
    maternity_leave_days = models.PositiveSmallIntegerField(default=84)

    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_code", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.country_code})"


class TaxBracket(models.Model):
    profile = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="tax_brackets")
    lower_bound = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    upper_bound = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0"))

    class Meta:
        ordering = ["lower_bound"]

    def __str__(self) -> str:
        upper = self.upper_bound if self.upper_bound is not None else "and up"
        return f"{self.profile.country_code} {self.lower_bound}-{upper} @ {self.rate}"


class ContributionRule(models.Model):
    profile = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="contribution_rules")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    employee_rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0"))
    employer_rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0"))
    cap_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["code"]
        unique_together = ("profile", "code")

    def __str__(self) -> str:
        return f"{self.profile.country_code} {self.code}"


class LedgerAccount(models.Model):
    class AccountType(models.TextChoices):
        ASSET = "ASSET", "Asset"
        LIABILITY = "LIABILITY", "Liability"
        EQUITY = "EQUITY", "Equity"
        INCOME = "INCOME", "Income"
        EXPENSE = "EXPENSE", "Expense"

    profile = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="ledger_accounts")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        unique_together = ("profile", "code")

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class JournalEntry(models.Model):
    profile = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="journal_entries")
    entry_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=64, blank=True)
    memo = models.CharField(max_length=255, blank=True)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.PositiveIntegerField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-id"]

    def __str__(self) -> str:
        return f"{self.entry_date} {self.reference or self.id}"


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="lines")
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.account} ({self.debit}/{self.credit})"


class Counterparty(models.Model):
    class CounterpartyType(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        GUARDIAN = "GUARDIAN", "Guardian"
        VENDOR = "VENDOR", "Vendor"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=200)
    counterparty_type = models.CharField(max_length=20, choices=CounterpartyType.choices, default=CounterpartyType.OTHER)
    student = models.ForeignKey(StudentProfile, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FeePlan(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="fee_plans",
    )
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="fee_plans")
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="fee_plans")
    specialty = models.ForeignKey(Specialty, on_delete=models.CASCADE, related_name="fee_plans")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["academic_year__start_date", "name"]
        unique_together = ("academic_year", "classroom", "specialty", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.classroom} / {self.specialty})"


class FeeItem(models.Model):
    class ItemType(models.TextChoices):
        TUITION = "TUITION", "Tuition"
        PTA = "PTA", "PTA Levy"
        WORKSHOP = "WORKSHOP", "Workshop Fee"
        ACTIVITY = "ACTIVITY", "Activity"
        TRANSPORT = "TRANSPORT", "Transport / Bus"
        CUSTOM = "CUSTOM", "Custom"

    plan = models.ForeignKey(FeePlan, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)
    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.TUITION)
    is_mandatory = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.amount})"


class FeeInstallment(models.Model):
    fee_item = models.ForeignKey(FeeItem, on_delete=models.CASCADE, related_name="installments")
    installment_number = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()

    class Meta:
        ordering = ["installment_number"]
        unique_together = ("fee_item", "installment_number")

    def __str__(self) -> str:
        return f"{self.fee_item} #{self.installment_number}"


class PaymentMethodCode(models.TextChoices):
    CASH = "CASH", "Cash"
    BANK = "BANK", "Bank Transfer"
    MTN_MOMO = "MTN_MOMO", "MTN MoMo"
    ORANGE_MOMO = "ORANGE_MOMO", "Orange Money"
    CHECK = "CHECK", "Check"
    WALLET = "WALLET", "Digital Wallet"
    OTHER = "OTHER", "Other"


class PaymentMethod(models.Model):
    METHOD_TYPES = [
        ("card", "Credit/Debit Card"),
        ("bank_transfer", "Bank Transfer"),
        ("wallet", "Digital Wallet"),
        ("mobile_money", "Mobile Money"),
        ("check", "Check"),
    ]

    GATEWAYS = [
        ("stripe", "Stripe"),
        ("paypal", "PayPal"),
        ("flutterwave", "Flutterwave"),
        ("paystack", "Paystack"),
        ("manual", "Manual Processing"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    method_type = models.CharField(max_length=20, choices=METHOD_TYPES)
    gateway = models.CharField(max_length=20, choices=GATEWAYS, null=True, blank=True)
    region = models.ForeignKey("siteconfig.RegionConfig", on_delete=models.CASCADE, related_name="payment_methods")
    is_active = models.BooleanField(default=True)

    api_key = models.CharField(max_length=500, blank=True, help_text="Encrypted API key")
    api_secret = models.CharField(max_length=500, blank=True, help_text="Encrypted secret")
    webhook_url = models.URLField(blank=True)
    webhook_secret = models.CharField(max_length=500, blank=True)

    transaction_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    fixed_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_payment_methods",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Payment Method"
        verbose_name_plural = "Payment Methods"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_method_type_display()})"

    def calculate_fee(self, amount: Decimal) -> Decimal:
        percent_fee = amount * (Decimal(self.transaction_fee_percent) / 100)
        return percent_fee + Decimal(self.fixed_fee)


class Invoice(models.Model):
    # Phase 4: Enable audit logging for this critical model (financial records)
    audit_enabled = True

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invoices",
    )
    class InvoiceType(models.TextChoices):
        AR = "AR", "Accounts Receivable"
        AP = "AP", "Accounts Payable"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PARTIAL = "PARTIAL", "Partially Paid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"
        VOID = "VOID", "Void"

    profile = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="invoices")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_type = models.CharField(max_length=5, choices=InvoiceType.choices, default=InvoiceType.AR)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    student = models.ForeignKey(StudentProfile, on_delete=models.SET_NULL, null=True, blank=True)
    counterparty = models.ForeignKey(Counterparty, on_delete=models.SET_NULL, null=True, blank=True)
    issued_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=64, blank=True)
    payment_code = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        db_index=True,
        help_text="Unique code for parent to quote when paying (e.g. MoMo). Auto-generated if blank.",
    )
    notes = models.TextField(blank=True)
    void_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Required when voiding: reason for voiding this invoice (audited).",
    )
    attachment = models.FileField(
        upload_to=_invoice_attachment_upload_to,
        blank=True,
        null=True,
        validators=[validate_document_file, validate_file_size_5mb],
        help_text="Optional PDF or image attachment for this invoice (max 5MB).",
    )
    # Payment proof fields for bank transfers and mobile money
    payment_proof = models.FileField(
        upload_to=_invoice_payment_proof_upload_to,
        blank=True,
        null=True,
        validators=[validate_receipt_file, validate_file_size_2mb],
        help_text="Upload proof of payment (receipt, screenshot, etc.) - max 2MB",
    )
    transaction_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Transaction ID or reference number from payment provider",
    )
    payment_notes = models.TextField(
        blank=True,
        help_text="Additional notes about the payment",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.01"))],  # Must be positive
    )
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    preferred_payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethodCode.choices,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Audit logging fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices_created',
        help_text="User who created this invoice"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices_updated',
        help_text="User who last updated this invoice"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft delete timestamp - set instead of deleting"
    )

    class Meta:
        ordering = ["-issued_date", "-id"]

    def clean(self):
        """Validate invoice data before saving."""
        if self.total_amount < Decimal("0.01"):
            raise ValidationError({"total_amount": "Invoice total must be at least 0.01"})
        # Validate preferred payment method against profile configuration when provided
        if self.preferred_payment_method:
            # If profile defines available methods, ensure preferred method is allowed
            if self.profile and isinstance(self.profile.available_payment_methods, list) and self.profile.available_payment_methods:
                if self.preferred_payment_method not in self.profile.available_payment_methods:
                    raise ValidationError({
                        "preferred_payment_method": (
                            f"Method '{self.preferred_payment_method}' is not allowed for profile {self.profile.name}. "
                            f"Allowed: {', '.join(self.profile.available_payment_methods)}"
                        )
                    })

    def save(self, *args, **kwargs):
        """
        Validate invoice and ensure a stable payment_code exists.
        Part F 25.1: Invoice immutability — once issued/paid, amount and key fields are read-only.
        Internal recalculation (from line add/delete or payment sync) is allowed via _recalculating.
        """
        skip_immutability = getattr(self, "_recalculating", False)
        if not skip_immutability and self.pk and self.status != self.Status.DRAFT:
            try:
                existing = type(self).objects.get(pk=self.pk)
                if existing.total_amount != self.total_amount or existing.invoice_type != self.invoice_type:
                    from django.core.exceptions import ValidationError
                    raise ValidationError(
                        {"total_amount": "Invoice amounts and type are immutable once status is not DRAFT (Part F 25.1)."}
                    )
            except type(self).DoesNotExist:
                pass
        self.full_clean()
        super().save(*args, **kwargs)
        if not self.payment_code:
            short = uuid.uuid4().hex[:8].upper()
            code = f"INV-{self.id}-{short}"
            type(self).objects.filter(pk=self.pk, payment_code="").update(payment_code=code)
            self.payment_code = code
    
    @property
    def computed_balance(self) -> Decimal:
        """
        Compute remaining balance from total_amount - sum(payments).
        
        This replaces the denormalized balance_amount field with a reliable 
        computed property that always reflects the true state.
        
        Note: The balance_amount field is deprecated and should be migrated to 
        use this property. For now, both exist for backwards compatibility.
        """
        total_paid = sum(
            p.amount for p in self.payments.all()
        ) or Decimal("0.00")
        return max(self.total_amount - total_paid, Decimal("0.00"))
    
    def reconcile_balance(self) -> bool:
        """
        Sync the denormalized balance_amount field with computed value.
        Returns True if balance was out of sync and updated.
        
        This method should be called after payment changes to maintain 
        backwards compatibility with code that relies on balance_amount field.
        """
        correct_balance = self.computed_balance
        if self.balance_amount != correct_balance:
            self.balance_amount = correct_balance
            self.save(update_fields=['balance_amount', 'updated_at'])
            return True
        return False

    def __str__(self) -> str:
        return f"{self.invoice_type} {self.reference or self.id}"

    def delete(self, using=None, keep_parents=False, hard_delete: bool = False):
        """
        Soft delete by default for legal/compliance traceability.
        """
        if hard_delete:
            return super().delete(using=using, keep_parents=keep_parents)
        if self.deleted_at:
            return (0, {})
        self.deleted_at = timezone.now()
        fields = ["deleted_at", "updated_at"]
        if self.status != self.Status.VOID:
            self.status = self.Status.VOID
            fields.append("status")
        self.save(update_fields=fields)
        return (1, {self._meta.label: 1})

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee_item = models.ForeignKey(FeeItem, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.description


class Payment(models.Model):
    # Phase 4: Enable audit logging for this critical model (financial records)
    audit_enabled = True

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payments",
    )
    PURPOSE_CHOICES = [
        ("tuition", "Tuition"),
        ("exam_fee", "Exam Fee"),
        ("activity_fee", "Activity Fee"),
        ("accommodation", "Accommodation"),
        ("other", "Other"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments", null=True, blank=True)
    reference_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="payments", null=True, blank=True)
    region = models.ForeignKey("siteconfig.RegionConfig", on_delete=models.CASCADE, related_name="payments", null=True, blank=True)
    payment_method = models.ForeignKey("finance.PaymentMethod", on_delete=models.PROTECT, related_name="payments", null=True, blank=True)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],  # Must be positive
    )
    currency_code = models.CharField(max_length=3, default="USD")
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default="tuition")
    description = models.TextField(blank=True)
    method = models.CharField(max_length=20, choices=PaymentMethodCode.choices, blank=True, default="")
    reference = models.CharField(
        max_length=80,
        blank=True,
        help_text="Human-readable or internal reference; may mirror external_reference. See docs/DATA_PAYMENT_REFERENCE.md.",
    )
    paid_at = models.DateTimeField(default=timezone.now)
    receipt_number = models.CharField(max_length=64, blank=True)
    physical_receipt_book_serial = models.CharField(
        max_length=40,
        blank=True,
        help_text="Physical receipt book serial used at the bursar desk (for paper audit trail).",
    )
    physical_receipt_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Receipt number from the physical receipt book.",
    )
    external_reference = models.CharField(
        max_length=128,
        blank=True,
        help_text="External transaction ID (provider, bank, receipt). Use for matching and idempotency. See docs/DATA_PAYMENT_REFERENCE.md.",
    )
    gateway_transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True, default=None)
    gateway_response = models.JSONField(blank=True, default=dict)
    platform_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        help_text="Optional platform fee (e.g. Mobile Money) deducted and recorded.",
    )
    compliance_checked = models.BooleanField(default=False)
    compliance_issues = models.JSONField(blank=True, default=list)
    receipt_file = models.FileField(
        upload_to="finance/receipts/",
        blank=True,
        null=True,
        validators=[validate_receipt_file, validate_file_size_2mb],
        help_text="Optional uploaded receipt or slip (PDF/image, max 2MB).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    initiated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    # Status tracking (backwards compatible with external payment model expectations)
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status_reason = models.TextField(blank=True)
    
    # Audit logging fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments_created',
        help_text="User who recorded this payment"
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_payments",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft delete timestamp - set instead of deleting"
    )

    class Meta:
        ordering = ["-paid_at"]

    def clean(self):
        """Validate payment data before saving."""
        if self.amount < Decimal("0.01"):
            raise ValidationError({"amount": "Payment amount must be at least 0.01"})
        has_book = bool((self.physical_receipt_book_serial or "").strip())
        has_number = self.physical_receipt_number is not None
        if has_book != has_number:
            raise ValidationError({
                "physical_receipt_book_serial": "Provide both receipt book serial and receipt number.",
                "physical_receipt_number": "Provide both receipt book serial and receipt number.",
            })
        if (has_book or has_number) and self.method != PaymentMethodCode.CASH:
            raise ValidationError({
                "method": "Physical receipt serial can only be used for cash payments.",
            })
        if has_book and has_number:
            dupe_qs = Payment.objects.filter(
                physical_receipt_book_serial__iexact=self.physical_receipt_book_serial.strip(),
                physical_receipt_number=self.physical_receipt_number,
            )
            if self.pk:
                dupe_qs = dupe_qs.exclude(pk=self.pk)
            if dupe_qs.exists():
                raise ValidationError({
                    "physical_receipt_number": "This physical receipt serial/number is already used.",
                })
        
        # If invoice is set, check payment doesn't exceed balance
        if self.invoice:
            if not self.method:
                raise ValidationError({"method": "Payment method is required for invoice payments."})
            # Get total already paid (excluding this payment if editing)
            paid_amount = sum(
                p.amount for p in self.invoice.payments.exclude(pk=self.pk)
            ) or Decimal("0")
            remaining_balance = self.invoice.total_amount - paid_amount
            
            if self.amount > remaining_balance:
                raise ValidationError({
                    "amount": f"Payment {self.amount} exceeds remaining balance {remaining_balance}"
                })
        # Validate payment method against invoice profile's allowed methods
        if self.invoice and self.method:
            profile = self.invoice.profile
            if profile and isinstance(profile.available_payment_methods, list) and profile.available_payment_methods:
                if self.method not in profile.available_payment_methods:
                    raise ValidationError({
                        "method": (
                            f"Method '{self.method}' is not allowed for profile {profile.name}. "
                            f"Allowed: {', '.join(profile.available_payment_methods)}"
                        )
                    })

    def save(self, *args, **kwargs):
        """Call full_clean() before saving to validate."""
        if not self.reference_number:
            self.reference_number = uuid.uuid4().hex
        if self.gateway_transaction_id == "":
            self.gateway_transaction_id = None
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.reference_number:
            return f"{self.reference_number} {self.amount}"
        if self.invoice:
            return f"{self.invoice} {self.amount}"
        return f"Payment {self.pk} {self.amount}"

    def delete(self, using=None, keep_parents=False, hard_delete: bool = False):
        """
        Soft delete by default for payment audit integrity.
        """
        if hard_delete:
            return super().delete(using=using, keep_parents=keep_parents)
        if self.deleted_at:
            return (0, {})
        self.deleted_at = timezone.now()
        fields = ["deleted_at"]
        if self.status != "cancelled":
            self.status = "cancelled"
            fields.append("status")
        self.save(update_fields=fields)
        return (1, {self._meta.label: 1})

    def _get_audit_region(self):
        """Region for audit log: payment.region or payment_method.region."""
        if self.region_id:
            return self.region
        if self.payment_method_id and hasattr(self.payment_method, "region"):
            return getattr(self.payment_method, "region", None)
        return None

    def mark_processing(self) -> None:
        """Mark payment as processing."""
        self.status = "processing"
        self.initiated_at = timezone.now()
        self.save(update_fields=["status", "initiated_at"])
        region = self._get_audit_region()
        if region:
            PaymentAuditLog.objects.create(
                payment=self,
                region=region,
                action_type="payment_initiated",
                description="Payment marked as processing.",
                details={"status": "processing"},
                severity="medium",
            )

    def mark_completed(self, gateway_tx_id: str | None = None, response: dict | None = None) -> None:
        """Mark payment as completed."""
        self.status = "completed"
        self.completed_at = timezone.now()
        update_fields = ["status", "completed_at"]
        if gateway_tx_id:
            self.gateway_transaction_id = gateway_tx_id
            update_fields.append("gateway_transaction_id")
        if response is not None:
            self.gateway_response = response
            update_fields.append("gateway_response")
        self.save(update_fields=update_fields)
        region = self._get_audit_region()
        if region:
            PaymentAuditLog.objects.create(
                payment=self,
                region=region,
                action_type="payment_completed",
                description="Payment completed.",
                details={"gateway_transaction_id": gateway_tx_id} if gateway_tx_id else {},
                severity="low",
            )

    def mark_failed(self, reason: str = "", response: dict | None = None) -> None:
        """Mark payment as failed."""
        self.status = "failed"
        self.failed_at = timezone.now()
        self.status_reason = reason
        update_fields = ["status", "failed_at", "status_reason"]
        if response is not None:
            self.gateway_response = response
            update_fields.append("gateway_response")
        self.save(update_fields=update_fields)
        region = self._get_audit_region()
        if region:
            PaymentAuditLog.objects.create(
                payment=self,
                region=region,
                action_type="payment_failed",
                description="Payment failed.",
                details={"reason": reason},
                severity="high",
            )


class InvoicePayerShare(models.Model):
    """
    Split-billing obligations per guardian for one invoice.
    Allows independent reminders/late-fee workflows per payer.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PARTIAL = "PARTIAL", "Partially Paid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payer_shares",
    )
    guardian = models.ForeignKey(
        StudentGuardian,
        on_delete=models.CASCADE,
        related_name="invoice_payer_shares",
    )
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    late_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    is_active = models.BooleanField(default=True)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    last_late_fee_applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["invoice_id", "guardian_id"]
        unique_together = [("invoice", "guardian")]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_id} / Guardian {self.guardian_id} ({self.allocated_amount})"

    def clean(self):
        if self.allocated_amount <= Decimal("0.00"):
            raise ValidationError({"allocated_amount": "Allocated amount must be positive."})
        if self.paid_amount < Decimal("0.00"):
            raise ValidationError({"paid_amount": "Paid amount cannot be negative."})
        if self.invoice_id and self.guardian_id:
            if self.invoice.student_id and self.guardian.student_id != self.invoice.student_id:
                raise ValidationError({"guardian": "Guardian must belong to the invoice student."})

    @property
    def total_due(self) -> Decimal:
        return max((self.allocated_amount or Decimal("0.00")) + (self.late_fee_amount or Decimal("0.00")), Decimal("0.00"))

    @property
    def outstanding_amount(self) -> Decimal:
        return max(self.total_due - (self.paid_amount or Decimal("0.00")), Decimal("0.00"))

    def refresh_status(self, *, save: bool = True) -> str:
        now_date = timezone.localdate()
        if self.outstanding_amount <= Decimal("0.00"):
            next_status = self.Status.PAID
        elif self.paid_amount > Decimal("0.00"):
            next_status = self.Status.PARTIAL
        elif self.due_date and self.due_date < now_date:
            next_status = self.Status.OVERDUE
        else:
            next_status = self.Status.OPEN
        if self.status != next_status:
            self.status = next_status
            if save:
                self.save(update_fields=["status", "updated_at"])
        return next_status


class InvoicePayerSharePaymentAllocation(models.Model):
    """
    Allocation rows to make payer-share payment application idempotent.
    """

    payer_share = models.ForeignKey(
        InvoicePayerShare,
        on_delete=models.CASCADE,
        related_name="payment_allocations",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="payer_share_allocations",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        unique_together = [("payer_share", "payment")]

    def clean(self):
        if self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Allocation amount must be positive."})
        if self.payer_share_id and self.payment_id:
            if self.payer_share.invoice_id != self.payment.invoice_id:
                raise ValidationError({"payer_share": "Allocation payer-share must match payment invoice."})

    def __str__(self) -> str:
        return f"Payment {self.payment_id} -> Share {self.payer_share_id} ({self.amount})"


class ParentWallet(models.Model):
    """
    Per-parent/guardian wallet balance for "Pay with wallet" at checkout.
    One wallet per (school, user); balance in school currency.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="parent_wallets",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_wallets",
        help_text="Guardian/parent user who owns this wallet.",
    )
    currency_code = models.CharField(max_length=3, default=_default_currency)
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school_id", "user_id"]
        unique_together = [("school", "user")]

    def __str__(self) -> str:
        return f"Wallet {self.user_id} @ {self.school_id} ({self.balance} {self.currency_code})"


class WalletTransaction(models.Model):
    """Audit trail for wallet balance changes: top-up, payment, refund."""

    class Kind(models.TextChoices):
        TOP_UP = "top_up", "Top-up"
        PAYMENT = "payment", "Payment"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Adjustment"

    wallet = models.ForeignKey(
        ParentWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Positive = credit (top-up, refund); negative = debit (payment).",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Wallet balance after this transaction.",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_transactions",
    )
    reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount} @ {self.created_at}"


class CashOfficeClosure(models.Model):
    """
    Daily cash office closure to reconcile cash desk collections and deposits.
    Bridges digital ledger with physical cash-office controls.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    profile = models.ForeignKey(
        ComplianceProfile,
        on_delete=models.CASCADE,
        related_name="cash_office_closures",
    )
    closure_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    cash_collected = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    deposited_to_bank = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    cash_on_hand = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Physical cash count remaining in cashier's drawer at closure.",
    )
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discrepancy = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    bank_account = models.ForeignKey(
        "finance.BankAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_closures",
        help_text="Bank account where daily cash was deposited (if any).",
    )
    deposit_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_office_closures",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-closure_date", "-updated_at"]
        unique_together = ("profile", "closure_date")

    def clean(self):
        if self.opening_cash < 0 or self.cash_collected < 0 or self.deposited_to_bank < 0:
            raise ValidationError("Opening, collected, and deposited amounts cannot be negative.")
        if self.cash_on_hand < 0:
            raise ValidationError({"cash_on_hand": "Cash on hand cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        expected = (self.opening_cash or Decimal("0.00")) + (self.cash_collected or Decimal("0.00")) - (
            self.deposited_to_bank or Decimal("0.00")
        )
        self.expected_cash = expected
        self.discrepancy = (self.cash_on_hand or Decimal("0.00")) - expected
        if self.status == self.Status.CLOSED and not self.closed_at:
            self.closed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.profile.name} - {self.closure_date} ({self.get_status_display()})"


class Transaction(models.Model):
    TRANSACTION_TYPE = [
        ("payment", "Payment"),
        ("refund", "Refund"),
        ("chargeback", "Chargeback"),
        ("reversal", "Reversal"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE, default="payment")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    gateway_reference = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(blank=True, default=dict)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"

    def __str__(self) -> str:
        return f"{self.get_transaction_type_display()} - {self.amount} {self.currency} ({self.status})"


class RefundRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("processed", "Processed"),
    ]

    REASON_CHOICES = [
        ("duplicate", "Duplicate Payment"),
        ("incorrect_amount", "Incorrect Amount"),
        ("student_request", "Student Request"),
        ("overpayment", "Overpayment"),
        ("compliance", "Compliance Issue"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refund_requests")
    region = models.ForeignKey("siteconfig.RegionConfig", on_delete=models.CASCADE, related_name="refund_requests")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    status_notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_refunds",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_refunds",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Refund Request"
        verbose_name_plural = "Refund Requests"

    def __str__(self) -> str:
        return f"Refund: {self.payment.reference_number or self.payment.id} - {self.amount}"


class PaymentDispute(models.Model):
    """
    Full dispute flow for payments: raise, review, resolve (refund or no refund).
    Phase 9: Payments — full dispute, reconciliation, payout automation.
    """
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        RESOLVED_REFUND = "RESOLVED_REFUND", "Resolved (refund issued)"
        RESOLVED_NO_REFUND = "RESOLVED_NO_REFUND", "Resolved (no refund)"
        CLOSED = "CLOSED", "Closed"

    class Reason(models.TextChoices):
        DUPLICATE = "DUPLICATE", "Duplicate charge"
        NOT_RECEIVED = "NOT_RECEIVED", "Service not received"
        INCORRECT_AMOUNT = "INCORRECT_AMOUNT", "Incorrect amount"
        FRAUD = "FRAUD", "Suspected fraud"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="disputes",
    )
    region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.CASCADE,
        related_name="payment_disputes",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    reason = models.CharField(max_length=24, choices=Reason.choices)
    description = models.TextField()
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="raised_disputes",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_disputes",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment dispute"
        verbose_name_plural = "Payment disputes"

    def __str__(self) -> str:
        return f"Dispute {self.id} — {self.payment} ({self.get_status_display()})"


class PaymentReconciliation(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("reconciled", "Reconciled"),
        ("discrepancy", "Discrepancy Found"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    region = models.ForeignKey("siteconfig.RegionConfig", on_delete=models.CASCADE, related_name="payment_reconciliations")
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="reconciliations")
    period_start = models.DateField()
    period_end = models.DateField()
    total_payments = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_refunds = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_fees = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    discrepancy_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discrepancy_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciled_payments",
    )

    class Meta:
        ordering = ["-period_end"]
        verbose_name = "Payment Reconciliation"
        verbose_name_plural = "Payment Reconciliations"
        unique_together = [("region", "payment_method", "period_start", "period_end")]

    def __str__(self) -> str:
        return f"{self.region} - {self.payment_method.name} ({self.period_start} to {self.period_end})"


class PaymentAuditLog(models.Model):
    ACTION_TYPES = [
        ("payment_created", "Payment Created"),
        ("payment_initiated", "Payment Initiated"),
        ("payment_completed", "Payment Completed"),
        ("payment_failed", "Payment Failed"),
        ("refund_requested", "Refund Requested"),
        ("refund_approved", "Refund Approved"),
        ("transaction_recorded", "Transaction Recorded"),
        ("reconciliation_completed", "Reconciliation Completed"),
    ]

    SEVERITY_LEVELS = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    description = models.TextField()
    details = models.JSONField(blank=True, default=dict)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default="low")
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name="audit_logs")
    region = models.ForeignKey("siteconfig.RegionConfig", on_delete=models.CASCADE, related_name="payment_audit_logs")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_audit_logs",
    )

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Payment Audit Log"
        verbose_name_plural = "Payment Audit Logs"
        indexes = [
            models.Index(fields=["action_type", "timestamp"]),
            models.Index(fields=["region", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_type_display()} - {self.region}"


class PaymentReminder(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="reminder")
    reminder_days_before = models.JSONField(
        default=list,
        help_text="List of days before due date to send reminders, e.g., [7, 3, 1]. Falls back to SiteSettings default if empty."
    )
    reminder_channels = models.JSONField(
        default=list,
        help_text="Channels to use: ['email'], ['whatsapp'], ['email', 'sms'], etc. Falls back to SiteSettings default if empty."
    )
    next_send_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    message_template_email = models.TextField(
        default="Dear {guardian}, please pay {amount} for {invoice} by {due_date}.",
        help_text="Email message template"
    )
    message_template_sms = models.TextField(
        default="Reminder: Pay {amount} for {invoice} by {due_date}.",
        blank=True,
        help_text="SMS message template"
    )
    message_template_whatsapp = models.TextField(
        default="Hi {guardian}! 👋 Please pay *{amount}* for invoice *{invoice}* by *{due_date}*.",
        blank=True,
        help_text="WhatsApp message template"
    )

    class Meta:
        ordering = ["-invoice__due_date"]

    def __str__(self) -> str:
        return f"Reminder for {self.invoice}"

    def get_reminder_days(self):
        """Get reminder days from instance, then policy, then platform default (no SiteSettings.get_solo in tenant code)."""
        if self.reminder_days_before:
            return self.reminder_days_before
        school = getattr(self.invoice, "school", None)
        if school:
            try:
                from apps.policies.policy_registry import get_effective_policy
                policy = get_effective_policy(school)
                finance = (policy.get("finance") or {}) if isinstance(policy, dict) else {}
                days = finance.get("payment_reminder_default_days")
                if isinstance(days, list) and days:
                    return days
            except Exception:
                pass
        return [7, 3, 1]

    def get_reminder_channels(self):
        """Get reminder channels from instance, then policy, then platform default (no SiteSettings.get_solo in tenant code)."""
        if self.reminder_channels:
            return self.reminder_channels
        school = getattr(self.invoice, "school", None)
        if school:
            try:
                from apps.policies.policy_registry import get_effective_policy
                policy = get_effective_policy(school)
                finance = (policy.get("finance") or {}) if isinstance(policy, dict) else {}
                channels = finance.get("payment_reminder_default_channels")
                if isinstance(channels, list) and channels:
                    return channels
            except Exception:
                pass
        return ["email"]
    
    def get_message_template(self, channel: str) -> str:
        """Get message template for a specific channel."""
        if channel == "email":
            return self.message_template_email
        elif channel == "sms":
            return self.message_template_sms or self.message_template_email
        elif channel == "whatsapp":
            return self.message_template_whatsapp or self.message_template_email
        return self.message_template_email

    def schedule_next(self):
        """
        Schedule the next pending reminder slot.

        The reminder list is interpreted as "days before due date" milestones
        (for example [7, 3, 1]). After each send we move forward to the next
        future slot instead of reusing the first milestone again.
        """
        if not self.invoice.due_date:
            self.next_send_at = None
            self.save(update_fields=["next_send_at"])
            return

        raw_days = self.get_reminder_days()
        if not raw_days:
            self.next_send_at = None
            self.save(update_fields=["next_send_at"])
            return

        if isinstance(raw_days, (list, tuple)):
            day_values = raw_days
        else:
            day_values = [raw_days]

        milestones = []
        for day in day_values:
            try:
                parsed = float(day)
            except (TypeError, ValueError):
                continue
            if parsed < 0:
                continue
            milestones.append(parsed)

        if not milestones:
            self.next_send_at = None
            self.save(update_fields=["next_send_at"])
            return

        due_at = datetime.combine(self.invoice.due_date, datetime.min.time())
        due_at = timezone.make_aware(due_at, timezone=timezone.get_current_timezone())
        now = timezone.now()

        candidates = [
            due_at - timedelta(days=day)
            for day in sorted(set(milestones), reverse=True)
        ]
        future_candidates = [candidate for candidate in candidates if candidate > now]
        self.next_send_at = min(future_candidates) if future_candidates else None
        self.save(update_fields=["next_send_at"])


class PaymentReminderLog(models.Model):
    reminder = models.ForeignKey(PaymentReminder, on_delete=models.CASCADE, related_name="logs")
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="SENT")
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self) -> str:
        return f"{self.reminder} @ {self.sent_at}"


class Notification(models.Model):
    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ALERT = "ALERT", "Alert"

    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=256, blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_received",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.severity})"


class FinanceRequestAudit(models.Model):
    """Audit trail for finance access requests and notification actions."""

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="request_audits",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_request_audits",
    )
    action = models.CharField(max_length=64, default="marked_read")
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} ({self.notification_id})"


class ReportRequest(models.Model):
    class RequestStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"

    class ReportType(models.TextChoices):
        COLLECTION = "COLLECTION", "Collection summary"
        PAYROLL_LIABILITY = "PAYROLL_LIABILITY", "Payroll liability"
        CUSTOM = "CUSTOM", "Custom"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_requests",
    )
    report_type = models.CharField(max_length=40, choices=ReportType.choices)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.report_type} requested by {self.requested_by}"


class ReferralReward(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        PAID = "PAID", "Paid"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.PROTECT,
        related_name="referral_rewards",
    )
    guardian = models.ForeignKey(
        StudentGuardian,
        on_delete=models.PROTECT,
        related_name="referral_rewards",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    description = models.CharField(max_length=255, blank=True)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_rewards",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="awarded_referral_rewards",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} referral reward ({self.amount})"

    def mark_paid(self):
        self.status = self.Status.PAID
        self.save(update_fields=["status"])


class Budget(models.Model):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="budgets")
    name = models.CharField(max_length=120)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["academic_year__start_date", "name"]

    def __str__(self) -> str:
        return self.name


class BudgetLine(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.budget} {self.amount}"


class AssetCategory(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Asset(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DISPOSED = "DISPOSED", "Disposed"
        MAINTENANCE = "MAINTENANCE", "Maintenance"

    category = models.ForeignKey(AssetCategory, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    asset_tag = models.CharField(max_length=80, blank=True)
    location = models.CharField(max_length=120, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    salvage_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    useful_life_years = models.PositiveSmallIntegerField(default=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Grant(models.Model):
    name = models.CharField(max_length=200)
    funder = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "name"]

    def __str__(self) -> str:
        return self.name


class GrantAllocation(models.Model):
    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="allocations")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.grant} {self.amount}"


class WebhookLog(models.Model):
    """Audit trail for payment webhook processing.
    
    Tracks all incoming webhooks for debugging, compliance, and duplicate detection.
    """
    
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        VALIDATED = "VALIDATED", "Validated"
        PROCESSING = "PROCESSING", "Processing"
        PROCESSED = "PROCESSED", "Successfully Processed"
        FAILED = "FAILED", "Failed"
        DUPLICATE = "DUPLICATE", "Duplicate (Already Processed)"
        INVALID = "INVALID", "Invalid Data"

    provider = models.CharField(max_length=50)
    reference_id = models.CharField(max_length=255)
    client_ip = models.GenericIPAddressField()
    signature_valid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    request_body = models.TextField(blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_logs"
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_logs"
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "reference_id", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["client_ip", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.reference_id} {self.status}"


class PaymentProofUpload(models.Model):
    """
    Tracks payment receipt uploads from parents/guardians.
    Supports automated verification and payment application.
    """
    
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Verification"
        VERIFYING = "VERIFYING", "Verifying"
        VERIFIED = "VERIFIED", "Verified - Payment Applied"
        DISCREPANCY = "DISCREPANCY", "Discrepancy - Needs Review"
        REJECTED = "REJECTED", "Rejected"
    
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payment_proof_uploads"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payment_proof_uploads",
        help_text="Parent/guardian who uploaded the receipt"
    )
    receipt_file = models.FileField(
        upload_to="finance/payment_proofs/",
        validators=[validate_receipt_file, validate_file_size_2mb],
        help_text="Uploaded receipt file (PDF/image, max 2MB)"
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethodCode.choices,
        help_text="Payment method used (CASH, BANK, etc.)"
    )
    transaction_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Transaction reference/ID from receipt (optional, can be extracted)"
    )
    uploaded_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount from receipt (optional, can be extracted via OCR)"
    )
    verification_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extracted data from receipt (amount, reference, date, confidence)"
    )
    verification_confidence = models.FloatField(
        default=0.0,
        help_text="Confidence score (0.0-1.0) for verification"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proof_uploads",
        help_text="Created payment record (if verified and applied)"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_payment_proofs",
        help_text="Admin who verified (if manual verification)"
    )
    verification_notes = models.TextField(
        blank=True,
        help_text="Notes about verification (discrepancies, reasons for rejection, etc.)"
    )
    verification_reason = models.TextField(
        blank=True,
        help_text="Reason for manual approve/reject (required when overriding auto-verification)."
    )
    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Client key to prevent duplicate uploads on retry."
    )
    reassign_to_invoice = models.ForeignKey(
        "finance.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Set to another invoice (e.g. same student) and save to reassign this receipt."
    )
    # Fraud detection fields
    fraud_risk_score = models.IntegerField(
        default=0,
        help_text="Fraud risk score (0-100). Higher = more suspicious."
    )
    fraud_flags = models.JSONField(
        default=list,
        blank=True,
        help_text="List of fraud flags: ['old_receipt', 'duplicate_reference', 'date_mismatch', etc.]"
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hash of receipt file for duplicate detection"
    )
    receipt_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date extracted from receipt (for date validation)"
    )
    is_suspicious = models.BooleanField(
        default=False,
        help_text="Flagged as suspicious - requires manual review"
    )
    flagged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this receipt was flagged as suspicious"
    )
    flagged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flagged_receipts",
        help_text="Admin who flagged this receipt (if manual flag)"
    )
    # Bank deposit verification fields
    bank_verified = models.BooleanField(
        default=False,
        help_text="Whether deposit was verified in bank statements"
    )
    bank_verification_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When bank verification was performed"
    )
    bank_verification_method = models.CharField(
        max_length=50,
        blank=True,
        help_text="How deposit was verified: 'transaction_reference', 'amount_and_date', 'manual', etc."
    )
    bank_statement_entry = models.ForeignKey(
        "finance.BankStatementEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt_uploads",
        help_text="Matched bank statement entry"
    )
    bank_verification_notes = models.TextField(
        blank=True,
        help_text="Notes about bank verification"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of uploader (for fraud detection)"
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        help_text="User agent/browser info (for fraud detection)"
    )
    device_fingerprint = models.CharField(
        max_length=100,
        blank=True,
        help_text="Device fingerprint hash (for fraud detection)"
    )
    # Delayed verification tracking
    verification_retry_count = models.IntegerField(
        default=0,
        help_text="Number of times bank verification has been retried"
    )
    last_verification_attempt = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time bank verification was attempted"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.reassign_to_invoice_id and self.reassign_to_invoice_id != self.invoice_id:
            old_invoice_id = self.invoice_id
            self.invoice_id = self.reassign_to_invoice_id
            self.status = PaymentProofUpload.Status.PENDING
            self.verification_notes = (self.verification_notes or "") + f" [Reassigned from invoice {old_invoice_id}.] "
            self.reassign_to_invoice_id = None
            self.payment_id = None
            self.verified_by_id = None
            self.verified_at = None
            self.verification_reason = ""
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Proof Upload"
        verbose_name_plural = "Payment Proof Uploads"
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["invoice", "-created_at"]),
            models.Index(fields=["uploaded_by", "-created_at"]),
            models.Index(fields=["is_suspicious", "-created_at"]),
            models.Index(fields=["file_hash"]),
            models.Index(fields=["transaction_reference"]),
        ]
    
    def __str__(self) -> str:
        return f"Receipt upload for Invoice {self.invoice.id} - {self.get_status_display()}"


class BankAccount(models.Model):
    """
    School bank accounts for deposit verification.
    Supports Cameroon banks, MTN MoMo, Orange Money.
    """
    
    class AccountType(models.TextChoices):
        BANK = "BANK", "Bank Account"
        MTN_MOMO = "MTN_MOMO", "MTN Mobile Money"
        ORANGE_MONEY = "ORANGE_MONEY", "Orange Money"
        OTHER = "OTHER", "Other"
    
    name = models.CharField(
        max_length=200,
        help_text="Account name/nickname (e.g., 'Main School Account', 'MTN MoMo Merchant')"
    )
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.BANK
    )
    account_number = models.CharField(
        max_length=50,
        help_text="Account number (bank account, MoMo merchant number, etc.)"
    )
    bank_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Bank name (for bank accounts)"
    )
    branch = models.CharField(
        max_length=100,
        blank=True,
        help_text="Branch name/location"
    )
    currency = models.CharField(
        max_length=3,
        default=_default_currency,
        help_text="Currency code (ISO 4217, e.g. USD, XAF, EUR)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this account is currently active"
    )
    region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.CASCADE,
        related_name="bank_accounts"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this account"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
        verbose_name = "Bank Account"
        verbose_name_plural = "Bank Accounts"
    
    def __str__(self) -> str:
        return f"{self.name} ({self.get_account_type_display()})"


class BankStatementEntry(models.Model):
    """
    Bank statement transactions for deposit verification.
    Can be imported from bank statements or entered manually.
    """
    
    class TransactionType(models.TextChoices):
        DEPOSIT = "DEPOSIT", "Deposit"
        WITHDRAWAL = "WITHDRAWAL", "Withdrawal"
        TRANSFER_IN = "TRANSFER_IN", "Transfer In"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
        FEE = "FEE", "Fee"
        OTHER = "OTHER", "Other"
    
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name="statement_entries"
    )
    transaction_date = models.DateField(
        help_text="Date of transaction"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Transaction amount (positive for deposits, negative for withdrawals)"
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.DEPOSIT
    )
    transaction_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Transaction reference/ID from bank"
    )
    description = models.TextField(
        blank=True,
        help_text="Transaction description/details"
    )
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Account balance after this transaction"
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Whether this entry has been verified/matched"
    )
    matched_receipt_upload = models.ForeignKey(
        PaymentProofUpload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_statements",
        help_text="Receipt upload that matches this statement entry"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    imported_from = models.CharField(
        max_length=200,
        blank=True,
        help_text="Source of this entry (e.g., 'Bank Statement Upload', 'Manual Entry')"
    )
    
    class Meta:
        ordering = ["-transaction_date", "-id"]
        verbose_name = "Bank Statement Entry"
        verbose_name_plural = "Bank Statement Entries"
        indexes = [
            models.Index(fields=["bank_account", "transaction_date"]),
            models.Index(fields=["transaction_reference"]),
            models.Index(fields=["is_verified"]),
        ]
    
    def __str__(self) -> str:
        return f"{self.bank_account.name} - {self.transaction_date} - {self.amount}"


class BankStatementUpload(models.Model):
    """
    Tracks bank statement file uploads for import.
    """
    
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Import"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
    
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name="statement_uploads"
    )
    statement_file = models.FileField(
        upload_to="finance/bank_statements/",
        help_text="Bank statement file (CSV, PDF, Excel)"
    )
    statement_period_start = models.DateField(
        help_text="Start date of statement period"
    )
    statement_period_end = models.DateField(
        help_text="End date of statement period"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    entries_imported = models.IntegerField(
        default=0,
        help_text="Number of entries imported"
    )
    errors = models.JSONField(
        default=list,
        blank=True,
        help_text="Import errors (if any)"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bank_statement_uploads"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bank Statement Upload"
        verbose_name_plural = "Bank Statement Uploads"
    
    def __str__(self) -> str:
        return f"{self.bank_account.name} - {self.statement_period_start} to {self.statement_period_end}"


class SuspensePayment(models.Model):
    """
    Unidentified money awaiting manual claim/allocation.
    Typical case: MoMo/bank transfer with no clear student identifier.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PARTIAL = "PARTIAL", "Partially Allocated"
        RESOLVED = "RESOLVED", "Resolved"

    bank_statement_entry = models.OneToOneField(
        BankStatementEntry,
        on_delete=models.CASCADE,
        related_name="suspense_payment",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=_default_currency)
    transaction_reference = models.CharField(max_length=100, blank=True)
    payer_name = models.CharField(max_length=120, blank=True)
    payer_phone = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    suggested_student = models.ForeignKey(
        StudentProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggested_suspense_payments",
    )
    suggested_invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggested_suspense_payments",
    )
    claimed_student = models.ForeignKey(
        StudentProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_suspense_payments",
    )
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_suspense_payments",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["transaction_reference"]),
        ]

    def __str__(self) -> str:
        ref = self.transaction_reference or f"SUSP-{self.pk}"
        return f"{ref} ({self.amount} {self.currency})"

    @property
    def allocated_amount(self) -> Decimal:
        total = self.allocations.aggregate(total=models.Sum("amount")).get("total")
        return total or Decimal("0.00")

    @property
    def remaining_amount(self) -> Decimal:
        return max((self.amount or Decimal("0.00")) - self.allocated_amount, Decimal("0.00"))


class SuspensePaymentAllocation(models.Model):
    """Allocation lines that split one suspense payment across one or more invoices."""

    suspense_payment = models.ForeignKey(
        SuspensePayment,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="suspense_allocations",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suspense_allocations",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suspense_allocations_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        unique_together = [("suspense_payment", "invoice")]

    def clean(self):
        if self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Allocation amount must be positive."})

    def __str__(self) -> str:
        return f"{self.suspense_payment_id} -> {self.invoice_id} ({self.amount})"


# =============================================================================
# Financial Aid & Scholarships (Phase 1 — global platform, any region)
# =============================================================================


class AwardSource(models.Model):
    """
    Fund bucket for scholarships/grants. Tenant-scoped (school_id).
    total_budget / remaining_funds; currency for multi-currency support.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="award_sources",
    )
    name = models.CharField(max_length=200, help_text="e.g. Endowment Fund, Donor X Grant")
    total_budget = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    remaining_funds = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Award source"
        verbose_name_plural = "Award sources"

    def __str__(self) -> str:
        return f"{self.name} ({self.school_id})"


class Scholarship(models.Model):
    """
    Scholarship definition linked to an AwardSource. eligibility_criteria is JSON-Logic
    (evaluated via nuance engine / check_eligibility). award_amount per award; is_renewable.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="scholarships",
    )
    source = models.ForeignKey(
        AwardSource,
        on_delete=models.PROTECT,
        related_name="scholarships",
    )
    title = models.CharField(max_length=200)
    eligibility_criteria = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON-Logic rules; context: gpa, sibling_count, student_tags, custom_attributes, attendance_rate, fee_status",
    )
    award_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    is_renewable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "Scholarship"
        verbose_name_plural = "Scholarships"

    def __str__(self) -> str:
        return f"{self.title} ({self.source.name})"


class FinancialAidApplication(models.Model):
    """
    Student application for a scholarship. Status flow: SUBMITTED -> APPROVED/REJECTED -> DISBURSED.
    eligibility_failure_reason stored for appeals; dispute_link for AccessRequest (SCHOLARSHIP_APPEAL).
    """
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        DISBURSED = "DISBURSED", "Disbursed"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="financial_aid_applications",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="financial_aid_applications",
    )
    scholarship = models.ForeignKey(
        Scholarship,
        on_delete=models.PROTECT,
        related_name="applications",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    amount_approved = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    eligibility_failure_reason = models.TextField(
        blank=True,
        help_text="Reason from check_eligibility or AI for appeal/dispute",
    )
    disbursed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_aid_applications_created",
    )
    # Optional link to dispute/appeal (AccessRequest with type SCHOLARSHIP_APPEAL)
    dispute_link = models.ForeignKey(
        "requests.AccessRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_aid_applications",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Financial aid application"
        verbose_name_plural = "Financial aid applications"
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["student", "scholarship"]),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.scholarship.title} ({self.get_status_display()})"


class AidAuditLog(models.Model):
    """Log every AwardSource balance change and disbursement for audit trail."""
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="aid_audit_logs",
    )
    source = models.ForeignKey(
        AwardSource,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    action = models.CharField(
        max_length=40,
        help_text="e.g. disbursement, donation, adjustment, refund",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    balance_after = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="remaining_funds after this action",
    )
    reason = models.CharField(max_length=255, blank=True)
    application = models.ForeignKey(
        FinancialAidApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_log_entries",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aid_audit_log_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Aid audit log"
        verbose_name_plural = "Aid audit logs"

    def __str__(self) -> str:
        return f"{self.source.name} {self.action} {self.amount} @ {self.created_at}"


# Section 15.3: Payment plans and recurring subscriptions (re-introduced after 0045 removal).
class PaymentPlan(models.Model):
    """Recurring payment plan (frequency, installments, grace period). Integrates with Invoice/Payment."""
    FREQUENCY_CHOICES = [
        ("WEEKLY", "Weekly"),
        ("BIWEEKLY", "Bi-Weekly"),
        ("MONTHLY", "Monthly"),
        ("QUARTERLY", "Quarterly"),
        ("ANNUALLY", "Annually"),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    max_installments = models.IntegerField(help_text="Total number of payments, 0 for unlimited")
    grace_period_days = models.IntegerField(default=0)
    late_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    early_payment_discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Discount for paying before due date",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} - {self.amount} {self.frequency}"


class RecurringPaymentSubscription(models.Model):
    """User subscription to a payment plan. Extends Invoice/Payment with recurring capability."""
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("PAUSED", "Paused"),
        ("CANCELLED", "Cancelled"),
        ("COMPLETED", "Completed"),
        ("DEFAULTED", "Defaulted"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_subscriptions",
    )
    plan = models.ForeignKey(PaymentPlan, on_delete=models.PROTECT)
    start_date = models.DateField()
    next_payment_date = models.DateField()
    last_payment_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    payments_made = models.IntegerField(default=0)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    missed_payments = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    payment_processor = models.CharField(max_length=50, default="manual")
    customer_payment_method_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_payment_date"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.plan.name}"
