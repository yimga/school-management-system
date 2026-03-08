from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.db import models, transaction
from django.utils import timezone

from apps.finance.models import ComplianceProfile, ContributionRule, TaxBracket
from apps.people.models import TeacherProfile
from apps.platform_runtime.helpers import get_effective_site_settings

from .models import (
    EmploymentContract,
    PayrollEmployee,
    PayrollRun,
    Payslip,
    PayslipLine,
    SalaryAdjustment,
)


def _active_contract(employee: PayrollEmployee, as_of) -> EmploymentContract | None:
    return (
        employee.contracts.filter(is_active=True, start_date__lte=as_of)
        .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=as_of))
        .order_by("-start_date")
        .first()
    )


def _teacher_profile(employee: PayrollEmployee) -> TeacherProfile | None:
    try:
        return employee.user.teacher_profile
    except TeacherProfile.DoesNotExist:
        return None


def _resolve_compensation(
    employee: PayrollEmployee,
    profile: ComplianceProfile,
    period_end,
):
    contract = _active_contract(employee, period_end)
    teacher_profile = _teacher_profile(employee)

    pay_type = contract.pay_type if contract else employee.pay_type
    base_salary = (
        (contract.base_salary if contract else None)
        or employee.base_salary
        or (teacher_profile.salary_amount if teacher_profile else None)
        or Decimal("0.00")
    )
    hourly_rate = (
        (contract.hourly_rate if contract else None)
        or employee.hourly_rate
        or Decimal("0.00")
    )
    salary_cap = (
        (contract.salary_cap if contract else None)
        or employee.salary_cap
        or (teacher_profile.salary_cap if teacher_profile else None)
    )
    hours_per_week = (
        (contract.hours_per_week if contract else None)
        or profile.default_hours_per_week
    )
    overtime_multiplier = (
        (contract.overtime_multiplier if contract else None)
        or profile.overtime_multiplier
    )
    return pay_type, base_salary, hourly_rate, salary_cap, hours_per_week, overtime_multiplier


def get_active_payroll_profile(*, school=None) -> ComplianceProfile | None:
    site = get_effective_site_settings(school=school)
    if getattr(site, "compliance_profile", None):
        return site.compliance_profile
    return ComplianceProfile.objects.filter(is_active=True).first()


def _sum_hours(employee: PayrollEmployee, period_start, period_end) -> Decimal:
    qs = employee.time_entries.filter(entry_date__gte=period_start, entry_date__lte=period_end)
    if qs.filter(is_approved=True).exists():
        qs = qs.filter(is_approved=True)
    total = qs.aggregate(total=models.Sum("hours_worked")).get("total")
    return total or Decimal("0.00")


def calculate_tax(profile: ComplianceProfile, gross: Decimal) -> Decimal:
    tax = Decimal("0.00")
    for bracket in TaxBracket.objects.filter(profile=profile).order_by("lower_bound"):
        if gross <= bracket.lower_bound:
            continue
        upper = bracket.upper_bound if bracket.upper_bound is not None else gross
        taxable = min(gross, upper) - bracket.lower_bound
        if taxable > 0:
            tax += taxable * bracket.rate
    return tax


def calculate_contributions(profile: ComplianceProfile, gross: Decimal):
    contributions = []
    employee_total = Decimal("0.00")
    employer_total = Decimal("0.00")
    for rule in ContributionRule.objects.filter(profile=profile).order_by("code"):
        base = gross
        if rule.cap_amount is not None:
            base = min(base, rule.cap_amount)
        employee_amount = base * rule.employee_rate
        employer_amount = base * rule.employer_rate
        contributions.append({
            "code": rule.code,
            "name": rule.name,
            "employee_amount": employee_amount,
            "employer_amount": employer_amount,
        })
        employee_total += employee_amount
        employer_total += employer_amount
    return contributions, employee_total, employer_total


def calculate_payroll(
    employee: PayrollEmployee,
    profile: ComplianceProfile,
    period_start,
    period_end,
):
    (
        pay_type,
        base_salary,
        hourly_rate,
        salary_cap,
        hours_per_week,
        overtime_multiplier,
    ) = _resolve_compensation(employee, profile, period_end)

    period_days = max((period_end - period_start).days + 1, 1)
    standard_hours = Decimal(str(hours_per_week)) * (Decimal(period_days) / Decimal("7"))
    total_hours = _sum_hours(employee, period_start, period_end)

    if pay_type == PayrollEmployee.PayType.HOURLY:
        base_pay = hourly_rate * total_hours
    else:
        base_pay = base_salary
        if total_hours > 0 and standard_hours > 0:
            base_pay = base_salary * min(total_hours, standard_hours) / standard_hours

    adjustments = SalaryAdjustment.objects.filter(
        employee=employee,
        effective_date__lte=period_end,
    )
    recurring = list(adjustments.filter(is_recurring=True))
    one_off = list(adjustments.filter(is_recurring=False, effective_date__gte=period_start))

    adjustment_total = sum((adj.amount for adj in recurring), Decimal("0.00"))
    adjustment_total += sum((adj.amount for adj in one_off), Decimal("0.00"))

    overtime_pay = Decimal("0.00")
    if total_hours > standard_hours and standard_hours > 0:
        rate = hourly_rate
        if rate <= 0 and base_salary > 0:
            rate = base_salary / standard_hours
        overtime_hours = total_hours - standard_hours
        overtime_pay = overtime_hours * rate * Decimal(str(overtime_multiplier))

    gross_pay = base_pay + adjustment_total + overtime_pay
    if salary_cap is not None and gross_pay > salary_cap:
        gross_pay = salary_cap

    if pay_type == PayrollEmployee.PayType.MONTHLY and gross_pay < profile.min_wage:
        gross_pay = profile.min_wage

    tax_amount = calculate_tax(profile, gross_pay)
    contributions, employee_contrib, employer_contrib = calculate_contributions(profile, gross_pay)

    net_pay = gross_pay - tax_amount - employee_contrib
    details = {
        "base_pay": base_pay,
        "adjustments": [
            {"amount": adj.amount, "description": adj.description, "effective_date": adj.effective_date}
            for adj in (recurring + one_off)
        ],
        "overtime_pay": overtime_pay,
        "contributions": contributions,
    }

    return {
        "gross_pay": gross_pay,
        "net_pay": net_pay,
        "tax_amount": tax_amount,
        "employee_contributions": employee_contrib,
        "employer_contributions": employer_contrib,
        "overtime_pay": overtime_pay,
        "total_hours": total_hours,
        "details": details,
    }


@transaction.atomic
def generate_payslips(run: PayrollRun, employees: Iterable[PayrollEmployee] | None = None) -> list[Payslip]:
    if employees is None:
        employees = PayrollEmployee.objects.filter(is_active=True).select_related("user")

    payslips: list[Payslip] = []
    for employee in employees:
        calc = calculate_payroll(employee, run.profile, run.period_start, run.period_end)
        payslip, _ = Payslip.objects.update_or_create(
            payroll_run=run,
            employee=employee,
            defaults={
                "gross_pay": calc["gross_pay"],
                "net_pay": calc["net_pay"],
                "tax_amount": calc["tax_amount"],
                "employee_contributions": calc["employee_contributions"],
                "employer_contributions": calc["employer_contributions"],
                "overtime_pay": calc["overtime_pay"],
                "total_hours": calc["total_hours"],
                "payment_method": employee.payment_method,
                "status": Payslip.Status.ISSUED,
                "details": calc["details"],
            },
        )
        if not payslip.reference:
            payslip.reference = f"PAY-{run.id}-{employee.id}"
            payslip.save(update_fields=["reference"])

        PayslipLine.objects.filter(payslip=payslip).delete()
        PayslipLine.objects.create(
            payslip=payslip,
            line_type=PayslipLine.LineType.EARNING,
            label="Base Pay",
            amount=calc["details"]["base_pay"],
        )
        if calc["overtime_pay"] > 0:
            PayslipLine.objects.create(
                payslip=payslip,
                line_type=PayslipLine.LineType.EARNING,
                label="Overtime",
                amount=calc["overtime_pay"],
            )
        for adj in calc["details"]["adjustments"]:
            label = adj.get("description") or "Adjustment"
            PayslipLine.objects.create(
                payslip=payslip,
                line_type=PayslipLine.LineType.EARNING,
                label=label,
                amount=adj.get("amount", Decimal("0.00")),
            )
        if calc["tax_amount"] > 0:
            PayslipLine.objects.create(
                payslip=payslip,
                line_type=PayslipLine.LineType.DEDUCTION,
                label="Tax",
                amount=calc["tax_amount"],
            )
        for contrib in calc["details"]["contributions"]:
            PayslipLine.objects.create(
                payslip=payslip,
                line_type=PayslipLine.LineType.CONTRIBUTION,
                code=contrib.get("code", ""),
                label=contrib.get("name", "Contribution"),
                amount=contrib.get("employee_amount", Decimal("0.00")),
                employer_amount=contrib.get("employer_amount", Decimal("0.00")),
            )

        payslips.append(payslip)

    run.status = PayrollRun.Status.PROCESSED
    run.processed_at = run.processed_at or timezone.now()
    run.save(update_fields=["status", "processed_at"])
    return payslips
