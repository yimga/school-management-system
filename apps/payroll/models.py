from decimal import Decimal

from django.conf import settings
from django.db import models
from apps.academics.models import Department
from apps.finance.models import ComplianceProfile


class PayrollEmployee(models.Model):
    class PayType(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        HOURLY = "HOURLY", "Hourly"

    class PaymentMethod(models.TextChoices):
        MTN_MOMO = "MTN_MOMO", "MTN Mobile Money"
        ORANGE_MOMO = "ORANGE_MOMO", "Orange Money"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        CHECK = "CHECK", "Check"
        CASH = "CASH", "Cash"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payroll_profile",
    )
    employee_code = models.CharField(max_length=50, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    pay_type = models.CharField(max_length=20, choices=PayType.choices, default=PayType.MONTHLY)
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hourly_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
    )
    bank_account = models.CharField(max_length=120, blank=True)
    mobile_money_number = models.CharField(max_length=50, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    cnps_number = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self) -> str:
        return self.user.get_full_name() or self.user.username


class EmploymentContract(models.Model):
    class ContractType(models.TextChoices):
        FIXED = "FIXED", "Fixed-term"
        INDEFINITE = "INDEFINITE", "Indefinite"

    employee = models.ForeignKey(PayrollEmployee, on_delete=models.CASCADE, related_name="contracts")
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.INDEFINITE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    pay_type = models.CharField(max_length=20, choices=PayrollEmployee.PayType.choices)
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hourly_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hours_per_week = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    overtime_multiplier = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.employee} ({self.contract_type})"


class SalaryAdjustment(models.Model):
    employee = models.ForeignKey(PayrollEmployee, on_delete=models.CASCADE, related_name="adjustments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    is_recurring = models.BooleanField(default=True)

    class Meta:
        ordering = ["-effective_date"]

    def __str__(self) -> str:
        return f"{self.employee} {self.amount}"


class TimeEntry(models.Model):
    employee = models.ForeignKey(PayrollEmployee, on_delete=models.CASCADE, related_name="time_entries")
    entry_date = models.DateField()
    hours_worked = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    is_approved = models.BooleanField(default=False)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-entry_date"]
        unique_together = ("employee", "entry_date")

    def __str__(self) -> str:
        return f"{self.employee} {self.entry_date}"


class LeaveRequest(models.Model):
    class LeaveType(models.TextChoices):
        ANNUAL = "ANNUAL", "Annual"
        SICK = "SICK", "Sick"
        MATERNITY = "MATERNITY", "Maternity"
        UNPAID = "UNPAID", "Unpaid"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    employee = models.ForeignKey(PayrollEmployee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveSmallIntegerField(default=0)
    is_paid = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_leaves",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.employee} {self.leave_type}"

    def save(self, *args, **kwargs):
        if self.start_date and self.end_date:
            self.days = max((self.end_date - self.start_date).days + 1, 0)
        super().save(*args, **kwargs)


class PayrollRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PROCESSED = "PROCESSED", "Processed"
        REVIEWED = "REVIEWED", "Reviewed"
        APPROVED = "APPROVED", "Approved"
        PAID = "PAID", "Paid"

    profile = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="payroll_runs")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-period_start", "-id"]

    def __str__(self) -> str:
        return f"Payroll {self.period_start} - {self.period_end}"


class PayrollRunApproval(models.Model):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="approvals")
    status = models.CharField(max_length=20, choices=PayrollRun.Status.choices)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_payroll_runs",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.run} -> {self.status}"


class Payslip(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PAID = "PAID", "Paid"

    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey(PayrollEmployee, on_delete=models.CASCADE, related_name="payslips")
    reference = models.CharField(max_length=64, blank=True)

    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    employee_contributions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    employer_contributions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    payment_method = models.CharField(
        max_length=20,
        choices=PayrollEmployee.PaymentMethod.choices,
        default=PayrollEmployee.PaymentMethod.BANK_TRANSFER,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-payroll_run__period_start", "employee__user__last_name"]
        unique_together = ("payroll_run", "employee")

    def __str__(self) -> str:
        return f"{self.employee} {self.payroll_run}"


class PayslipLine(models.Model):
    class LineType(models.TextChoices):
        EARNING = "EARNING", "Earning"
        DEDUCTION = "DEDUCTION", "Deduction"
        CONTRIBUTION = "CONTRIBUTION", "Contribution"

    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="lines")
    line_type = models.CharField(max_length=20, choices=LineType.choices)
    code = models.CharField(max_length=40, blank=True)
    label = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    employer_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.payslip} {self.label}"
