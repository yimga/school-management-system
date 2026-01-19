from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.siteconfig.models import SiteSettings
from apps.finance.models import ComplianceProfile

from .forms import LeaveRequestForm
from .models import LeaveRequest, PayrollEmployee, PayrollRun, Payslip
from .services import generate_payslips


def _active_profile() -> ComplianceProfile | None:
    site = SiteSettings.get_solo()
    if getattr(site, "compliance_profile", None):
        return site.compliance_profile
    return ComplianceProfile.objects.filter(is_active=True).first()


def _employee_for_user(user) -> PayrollEmployee | None:
    try:
        return user.payroll_profile
    except PayrollEmployee.DoesNotExist:
        return None


@staff_member_required
def dashboard(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    runs = PayrollRun.objects.filter(profile=profile).order_by("-period_start")[:12]
    latest_run = runs[0] if runs else None
    payslip_count = Payslip.objects.filter(payroll_run=latest_run).count() if latest_run else 0

    return render(request, "payroll/dashboard.html", {
        "profile": profile,
        "runs": runs,
        "latest_run": latest_run,
        "payslip_count": payslip_count,
    })


@staff_member_required
def run_detail(request: HttpRequest, run_id: int):
    run = get_object_or_404(PayrollRun, id=run_id)
    payslips = Payslip.objects.filter(payroll_run=run).select_related("employee", "employee__user")
    totals = payslips.aggregate(
        gross=models.Sum("gross_pay"),
        net=models.Sum("net_pay"),
        taxes=models.Sum("tax_amount"),
    )
    return render(request, "payroll/run_detail.html", {
        "run": run,
        "payslips": payslips,
        "totals": totals,
    })


@staff_member_required
def generate_run(request: HttpRequest, run_id: int):
    run = get_object_or_404(PayrollRun, id=run_id)
    if run.status == PayrollRun.Status.PAID:
        messages.error(request, "This payroll run is already paid.")
        return redirect("payroll:run_detail", run_id=run.id)

    generate_payslips(run)
    messages.success(request, "Payslips generated.")
    return redirect("payroll:run_detail", run_id=run.id)


@login_required
def employee_payslips(request: HttpRequest):
    employee = _employee_for_user(request.user)
    if not employee:
        return HttpResponseForbidden("No payroll profile configured.")

    slips = Payslip.objects.filter(employee=employee).select_related("payroll_run")
    return render(request, "payroll/employee_payslips.html", {
        "employee": employee,
        "payslips": slips.order_by("-payroll_run__period_start"),
    })


@login_required
def employee_leave(request: HttpRequest):
    employee = _employee_for_user(request.user)
    if not employee:
        return HttpResponseForbidden("No payroll profile configured.")

    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            leave.status = LeaveRequest.Status.PENDING
            leave.is_paid = leave.leave_type != LeaveRequest.LeaveType.UNPAID
            leave.save()
            messages.success(request, "Leave request submitted.")
            return redirect("payroll:employee_leave")
        messages.error(request, "Please correct the errors below.")
    else:
        form = LeaveRequestForm()

    leaves = LeaveRequest.objects.filter(employee=employee).order_by("-start_date")
    return render(request, "payroll/employee_leave.html", {
        "employee": employee,
        "form": form,
        "leaves": leaves,
    })


@staff_member_required
def create_run(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    if request.method == "POST":
        start = request.POST.get("period_start")
        end = request.POST.get("period_end")
        if not start or not end:
            messages.error(request, "Please provide both period start and end dates.")
            return redirect("payroll:create_run")

        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect("payroll:create_run")

        if end_date < start_date:
            messages.error(request, "Period end must be after start date.")
            return redirect("payroll:create_run")

        run = PayrollRun.objects.create(
            profile=profile,
            period_start=start_date,
            period_end=end_date,
            created_by=request.user,
        )
        messages.success(request, "Payroll run created.")
        return redirect("payroll:run_detail", run_id=run.id)

    return render(request, "payroll/create_run.html", {
        "profile": profile,
        "today": timezone.now().date(),
    })
