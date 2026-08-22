from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.core.validators import MinValueValidator
from apps.academics.models import Department
from apps.finance.models import ComplianceProfile


class PayScale(models.Model):
    """
    Defines a pay scale/grade with salary ranges that can be applied to staff.
    Allows admins to create standardized pay structures and apply them to employees.
    """

    name = models.CharField(
        max_length=100,
        help_text="Name of the pay scale (e.g., 'Grade 1', 'Senior Teacher', 'Administrative Staff')",
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Short code for the pay scale (e.g., 'GR1', 'SEN', 'ADM')",
    )
    description = models.TextField(
        blank=True, help_text="Description of this pay scale and who it applies to"
    )

    # Salary range for this scale
    min_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Minimum salary for this pay scale",
    )
    max_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Maximum salary for this pay scale",
    )
    default_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Default starting salary when applying this scale (optional)",
    )

    # Department association (optional - can be department-specific or general)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pay_scales",
        help_text="Optional: Restrict this scale to a specific department",
    )

    # Status
    is_active = models.BooleanField(
        default=True, help_text="Only active scales can be applied to new employees"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_pay_scales",
    )

    class Meta:
        ordering = ["code", "name"]
        verbose_name = "Pay Scale"
        verbose_name_plural = "Pay Scales"
        indexes = [
            models.Index(fields=["code", "is_active"]),
            models.Index(fields=["department", "is_active"]),
        ]

    def __str__(self):
        dept = f" ({self.department.name})" if self.department else ""
        return f"{self.name} ({self.code}){dept}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.min_salary and self.max_salary:
            if self.min_salary > self.max_salary:
                raise ValidationError(
                    "Minimum salary cannot be greater than maximum salary."
                )
            if self.default_salary:
                if (
                    self.default_salary < self.min_salary
                    or self.default_salary > self.max_salary
                ):
                    raise ValidationError(
                        "Default salary must be within the min/max range."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def apply_to_employee(self, employee, use_default=True):
        """
        Apply this pay scale to an employee.
        Sets pay_grade and optionally salary_amount.

        Args:
            employee: PayrollEmployee or TeacherProfile instance
            use_default: If True, sets salary_amount to default_salary if available
        """
        if hasattr(employee, "pay_grade"):
            employee.pay_grade = self.code

        if use_default and self.default_salary and hasattr(employee, "salary_amount"):
            employee.salary_amount = self.default_salary
            employee.save(update_fields=["pay_grade", "salary_amount"])
        elif hasattr(employee, "pay_grade"):
            employee.save(update_fields=["pay_grade"])


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
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True
    )
    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    pay_type = models.CharField(
        max_length=20, choices=PayType.choices, default=PayType.MONTHLY
    )
    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    hourly_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    salary_cap = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # Link to pay scale
    pay_scale = models.ForeignKey(
        PayScale,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
        help_text="Pay scale/grade assigned to this employee",
    )

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

    employee = models.ForeignKey(
        PayrollEmployee, on_delete=models.CASCADE, related_name="contracts"
    )
    contract_type = models.CharField(
        max_length=20, choices=ContractType.choices, default=ContractType.INDEFINITE
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    pay_type = models.CharField(max_length=20, choices=PayrollEmployee.PayType.choices)
    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    hourly_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    salary_cap = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    hours_per_week = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    overtime_multiplier = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    # Link to pay scale for this contract
    pay_scale = models.ForeignKey(
        PayScale,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts",
        help_text="Pay scale for this contract period",
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.employee} ({self.contract_type})"


class SalaryAdjustment(models.Model):
    employee = models.ForeignKey(
        PayrollEmployee, on_delete=models.CASCADE, related_name="adjustments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    is_recurring = models.BooleanField(default=True)

    class Meta:
        ordering = ["-effective_date"]

    def __str__(self) -> str:
        return f"{self.employee} {self.amount}"


class TimeEntry(models.Model):
    employee = models.ForeignKey(
        PayrollEmployee, on_delete=models.CASCADE, related_name="time_entries"
    )
    entry_date = models.DateField()
    hours_worked = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
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

    employee = models.ForeignKey(
        PayrollEmployee, on_delete=models.CASCADE, related_name="leave_requests"
    )
    leave_type = models.CharField(
        max_length=20, choices=LeaveType.choices, default=LeaveType.ANNUAL
    )
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveSmallIntegerField(default=0)
    is_paid = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
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

    profile = models.ForeignKey(
        ComplianceProfile, on_delete=models.PROTECT, related_name="payroll_runs"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
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
    run = models.ForeignKey(
        PayrollRun, on_delete=models.CASCADE, related_name="approvals"
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    approved_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-approved_at"]


class Payslip(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PAID = "PAID", "Paid"

    payroll_run = models.ForeignKey(
        PayrollRun, on_delete=models.CASCADE, related_name="payslips"
    )
    employee = models.ForeignKey(
        PayrollEmployee, on_delete=models.CASCADE, related_name="payslips"
    )
    reference = models.CharField(max_length=64, blank=True)

    gross_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    net_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    employee_contributions = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    employer_contributions = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    overtime_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    other_deductions = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PayrollEmployee.PaymentMethod.choices,
        default=PayrollEmployee.PaymentMethod.BANK_TRANSFER,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # DjangoJSONEncoder is REQUIRED here, not cosmetic. services.calculate_payroll
    # builds this blob from model fields, so it always contains Decimals
    # (base_pay, overtime_pay, every adjustments[].amount and
    # contributions[].employee_amount/employer_amount) and a datetime.date
    # (adjustments[].effective_date). Without an encoder the plain json.dumps
    # behind JSONField raises "Object of type Decimal is not JSON serializable"
    # and generate_payslips dies for EVERY employee -- payroll cannot run at all.
    #
    # Safe to add: nothing reads Payslip.details back (it is a write-only audit
    # blob; the itemised figures live on PayslipLine and the header fields), so
    # DjangoJSONEncoder rendering Decimal as a string breaks no consumer.
    details = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ["-payroll_run__period_start", "employee__user__last_name"]
        unique_together = ("payroll_run", "employee")

    def __str__(self) -> str:
        return f"{self.employee} {self.payroll_run}"


class PayslipLine(models.Model):
    class LineType(models.TextChoices):
        EARNING = "EARNING", "Earning"
        DEDUCTION = "DEDUCTION", "Deduction"

    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="lines")
    line_type = models.CharField(max_length=20, choices=LineType.choices)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["payslip", "display_order", "line_type"]

    def __str__(self) -> str:
        return f"{self.payslip} {self.description}"


from .models_offline_capture import PayrollOfflineCaptureRecord  # noqa: E402,F401
