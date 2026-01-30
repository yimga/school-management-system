from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import LeaveRequestForm
from .models import LeaveRequest, PayrollEmployee, PayrollRun, Payslip
from .services import generate_payslips, get_active_payroll_profile


def _employee_for_user(user) -> PayrollEmployee | None:
    try:
        return user.payroll_profile
    except PayrollEmployee.DoesNotExist:
        return None


@staff_member_required
def dashboard(request: HttpRequest):
    profile = get_active_payroll_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    runs = PayrollRun.objects.filter(profile=profile).order_by("-period_start")[:12]
    latest_run = runs[0] if runs else None
    payslip_count = Payslip.objects.filter(payroll_run=latest_run).count() if latest_run else 0

    from apps.siteconfig.dashboard_views import load_dashboard_layout_settings, _can_customize
    from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata
    from django.urls import reverse
    from django.utils.safestring import mark_safe
    import json

    dashboard_settings = load_dashboard_layout_settings(request.user, "payroll")
    allow_custom_layout = _can_customize(request.user)
    dashboard_layout_url = reverse("api:dashboard-layout", kwargs={"page": "payroll"})
    available_sidebar_items = [
        {"id": "payroll-home", "label": "Payroll Home", "url": reverse("payroll:dashboard"), "icon": "bi-cash-stack"},
        {"id": "payroll-create", "label": "New Payroll Run", "url": reverse("payroll:create_run"), "icon": "bi-plus-circle"},
        {"id": "payroll-employee", "label": "My Payslips", "url": reverse("payroll:employee_payslips"), "icon": "bi-wallet2"},
        {"id": "payroll-leave", "label": "Leave Requests", "url": reverse("payroll:employee_leave"), "icon": "bi-calendar-check"},
    ]
    widget_meta_json = mark_safe(json.dumps(get_dashboard_widget_metadata()))

    return render(request, "payroll/dashboard.html", {
        "profile": profile,
        "runs": runs,
        "latest_run": latest_run,
        "payslip_count": payslip_count,
        "allow_custom_layout": allow_custom_layout,
        "dashboard_settings": dashboard_settings,
        "dashboard_layout_url": dashboard_layout_url,
        "available_sidebar_items": available_sidebar_items,
        "widget_meta_json": widget_meta_json,
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
    """Payslips for the current user only (user-centric HR)."""
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
    """Leave requests for the current user only (user-centric HR)."""
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
    profile = get_active_payroll_profile()
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
