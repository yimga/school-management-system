from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
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


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    BANK = "BANK", "Bank Transfer"
    MTN_MOMO = "MTN_MOMO", "MTN MoMo"
    ORANGE_MOMO = "ORANGE_MOMO", "Orange Money"
    CHECK = "CHECK", "Check"
    OTHER = "OTHER", "Other"


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
        choices=PaymentMethod.choices,
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

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],  # Must be positive
    )
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    receipt_number = models.CharField(max_length=64, blank=True)
    external_reference = models.CharField(max_length=128, blank=True)
    receipt_file = models.FileField(
        upload_to="finance/receipts/",
        blank=True,
        null=True,
        validators=[validate_receipt_file, validate_file_size_2mb],
        help_text="Optional uploaded receipt or slip (PDF/image, max 2MB).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Audit logging fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments_created',
        help_text="User who recorded this payment"
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
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.invoice} {self.amount}"


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
