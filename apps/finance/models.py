from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.people.models import StudentProfile


class ComplianceProfile(models.Model):
    class ChartTemplate(models.TextChoices):
        OHADA = "OHADA", "OHADA"
        GENERIC = "GENERIC", "Generic"

    name = models.CharField(max_length=120)
    country_code = models.CharField(max_length=2)
    currency_code = models.CharField(max_length=3, default="XAF")
    currency_symbol = models.CharField(max_length=8, default="XAF")
    timezone = models.CharField(max_length=64, default="Africa/Douala")
    chart_template = models.CharField(max_length=20, choices=ChartTemplate.choices, default=ChartTemplate.GENERIC)

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


class Invoice(models.Model):
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
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_date", "-id"]

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
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        BANK = "BANK", "Bank"
        MTN_MOMO = "MTN_MOMO", "MTN MoMo"
        ORANGE_MOMO = "ORANGE_MOMO", "Orange Money"
        CHECK = "CHECK", "Check"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    reference = models.CharField(max_length=80, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    receipt_number = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        return f"{self.invoice} {self.amount}"


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
