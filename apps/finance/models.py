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


class ComplianceProfile(models.Model):
    class ChartTemplate(models.TextChoices):
        OHADA = "OHADA", "OHADA"
        GENERIC = "GENERIC", "Generic"

    name = models.CharField(max_length=120)
    country_code = models.CharField(max_length=2)
    currency_code = models.CharField(max_length=3, default="XAF")
    currency_symbol = models.CharField(max_length=8, default="XAF")
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
        ACTIVITY = "ACTIVITY", "Activity"
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
    attachment = models.FileField(
        upload_to="finance/invoices/",
        blank=True,
        null=True,
        validators=[validate_document_file, validate_file_size_5mb],
        help_text="Optional PDF or image attachment for this invoice (max 5MB).",
    )
    # Payment proof fields for bank transfers and mobile money
    payment_proof = models.FileField(
        upload_to="finance/payment_proofs/",
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
        """Call full_clean() before saving to validate."""
        self.full_clean()
        super().save(*args, **kwargs)
    
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

    def save(self, *args, **kwargs):
        if not self.payment_code:
            # Unique code for MoMo/payment quote: INV-<id>-<short> (set after first save if needed)
            super().save(*args, **kwargs)
            if not self.payment_code:
                short = uuid.uuid4().hex[:8].upper()
                self.payment_code = f"INV-{self.id}-{short}"
                super().save(update_fields=["payment_code"])
            return
        super().save(*args, **kwargs)


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
    reference = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    receipt_number = models.CharField(max_length=64, blank=True)
    external_reference = models.CharField(max_length=128, blank=True)
    gateway_transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True, default=None)
    gateway_response = models.JSONField(blank=True, default=dict)
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

    def mark_processing(self) -> None:
        """Mark payment as processing."""
        self.status = "processing"
        self.initiated_at = timezone.now()
        self.save(update_fields=["status", "initiated_at"])

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
    reminder_days_before = models.PositiveSmallIntegerField(default=3)
    next_send_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    message_template = models.TextField(
        default="Dear {guardian}, please pay {amount} for {invoice} by {due_date}.",
    )

    class Meta:
        ordering = ["-invoice__due_date"]

    def __str__(self) -> str:
        return f"Reminder for {self.invoice}"

    def schedule_next(self):
        if not self.invoice.due_date:
            return
        target = datetime.combine(self.invoice.due_date, datetime.min.time())
        remind_at = target - timedelta(days=self.reminder_days_before)
        self.next_send_at = timezone.make_aware(remind_at, timezone=timezone.get_current_timezone())
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
