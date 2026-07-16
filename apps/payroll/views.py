from __future__ import annotations

import json
from datetime import date
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.db.models import Count
from django.utils import timezone

from apps.accounts.decorators import require_permission
from .forms import LeaveRequestForm
from .models import LeaveRequest, PayrollEmployee, PayrollRun, Payslip
from .services import (
    approve_payroll_run,
    generate_payslips,
    get_active_payroll_profile,
    mark_payroll_run_paid,
    review_payroll_run,
)


def _employee_for_user(user) -> PayrollEmployee | None:
    try:
        return user.payroll_profile
    except PayrollEmployee.DoesNotExist:
        return None


@require_permission("payroll.view", "payroll.manage")
def dashboard(request: HttpRequest):
    profile = get_active_payroll_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    runs = PayrollRun.objects.filter(profile=profile).order_by("-period_start")[:12]
    latest_run = runs[0] if runs else None
    payslip_count = (
        Payslip.objects.filter(payroll_run=latest_run).count() if latest_run else 0
    )

    # Chart data: run status distribution
    status_counts = list(
        PayrollRun.objects.filter(profile=profile)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    status_labels = dict(PayrollRun.Status.choices)
    chart_status_donut = {
        "type": "doughnut",
        "data": {
            "labels": [
                status_labels.get(sc["status"], sc["status"]) for sc in status_counts
            ],
            "datasets": [
                {
                    "data": [sc["count"] for sc in status_counts],
                    "backgroundColor": [
                        "#6c757d",
                        "#0d6efd",
                        "#ffc107",
                        "#198754",
                        "#20c997",
                    ][: len(status_counts)],
                }
            ],
        },
    }

    # Chart data: payroll volume over last 6 months
    all_runs = PayrollRun.objects.filter(profile=profile).values_list(
        "period_start", flat=True
    )
    monthly_map = defaultdict(int)
    for d in all_runs:
        if d:
            monthly_map[(d.year, d.month)] += 1
    now = timezone.now().date()
    month_series = []
    for i in range(5, -1, -1):
        y, m = now.year, now.month
        m -= i
        while m < 1:
            m += 12
            y -= 1
        key = (y, m)
        label = date(y, m, 1).strftime("%b %Y")
        count = monthly_map.get(key, 0)
        month_series.append({"label": label, "count": count})
    chart_volume_column = {
        "type": "bar",
        "data": {
            "labels": [m["label"] for m in month_series],
            "datasets": [
                {
                    "label": "Payroll runs",
                    "data": [m["count"] for m in month_series],
                    "backgroundColor": "rgba(13, 110, 253, 0.7)",
                    "borderColor": "#0d6efd",
                    "borderWidth": 1,
                }
            ],
        },
    }

    from apps.accounts.utils import get_dashboard_context
    from django.urls import reverse

    dashboard_context = get_dashboard_context(request.user, "payroll", request=request)
    dashboard_settings = dashboard_context.get("dashboard_settings", {})
    allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
    dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
    widget_meta_json = dashboard_context.get("widget_meta_json", "")
    available_sidebar_items = [
        {
            "id": "payroll-home",
            "label": "Payroll Home",
            "url": reverse("payroll:dashboard"),
            "icon": "bi-cash-stack",
        },
        {
            "id": "payroll-create",
            "label": "New Payroll Run",
            "url": reverse("payroll:create_run"),
            "icon": "bi-plus-circle",
        },
        {
            "id": "payroll-employee",
            "label": "My Payslips",
            "url": reverse("payroll:employee_payslips"),
            "icon": "bi-wallet2",
        },
        {
            "id": "payroll-leave",
            "label": "Leave Requests",
            "url": reverse("payroll:employee_leave"),
            "icon": "bi-calendar-check",
        },
    ]

    n_runs = PayrollRun.objects.filter(profile=profile).count()
    next_payroll_actions = [
        {"label": "New run", "url": reverse("payroll:create_run")},
    ]
    if latest_run:
        next_payroll_actions.append(
            {
                "label": "Open latest",
                "url": reverse("payroll:run_detail", args=[latest_run.id]),
            }
        )
    else:
        next_payroll_actions.append(
            {
                "label": "Employee payslips",
                "url": reverse("payroll:employee_payslips"),
            }
        )
    next_payroll_actions.append(
        {"label": "Backend home", "url": reverse("accounts:backend_dashboard")}
    )

    phase7_de = {
        "eyebrow": "Payroll home",
        "headline_label": "Latest run status",
        "headline_value": latest_run.get_status_display()
        if latest_run
        else "No runs yet",
        "headline_meta": profile.name,
        "metrics": [
            {
                "label": "Payslips (latest)",
                "value": payslip_count,
                "meta": "Current run",
                "status": "ok",
            },
            {
                "label": "Runs on file",
                "value": n_runs,
                "meta": "History",
                "status": "ok",
            },
            {
                "label": "Period",
                "value": f"{latest_run.period_start} → {latest_run.period_end}"
                if latest_run
                else "—",
                "meta": "Latest window",
                "status": "ok",
            },
        ],
        "urgent_queue": [
            {
                "title": "Start or open a payroll run",
                "url": reverse("payroll:create_run")
                if not latest_run
                else reverse("payroll:run_detail", args=[latest_run.id]),
                "hint": "Keep pay periods current.",
            }
        ],
        "next_actions": next_payroll_actions[:3],
        "activity": [
            {
                "title": "Payroll console",
                "meta": "Runs and payslips below.",
            }
        ],
    }

    return render(
        request,
        "payroll/dashboard.html",
        {
            "profile": profile,
            "runs": runs,
            "latest_run": latest_run,
            "payslip_count": payslip_count,
            "chart_status_donut_json": json.dumps(chart_status_donut),
            "chart_volume_column_json": json.dumps(chart_volume_column),
            "allow_custom_layout": allow_custom_layout,
            "dashboard_settings": dashboard_settings,
            "dashboard_layout_url": dashboard_layout_url,
            "available_sidebar_items": available_sidebar_items,
            "widget_meta_json": widget_meta_json,
            "phase7_de": phase7_de,
        },
    )


@require_permission("payroll.view", "payroll.manage")
@require_GET
def export_disbursement(request: HttpRequest, run_id: int):
    """CSV bank disbursement file for an approved/processed payroll run."""
    run = get_object_or_404(PayrollRun, id=run_id)
    if run.status not in (
        PayrollRun.Status.APPROVED,
        PayrollRun.Status.PROCESSED,
        PayrollRun.Status.REVIEWED,
        PayrollRun.Status.PAID,
    ):
        messages.error(
            request,
            "Export is available after the run is processed or approved.",
        )
        return redirect("payroll:run_detail", run_id=run.id)

    from .disbursement_export import build_disbursement_csv, disbursement_filename

    csv_text = build_disbursement_csv(run)
    response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{disbursement_filename(run)}"'
    )
    return response


@require_permission("payroll.view", "payroll.manage")
def run_detail(request: HttpRequest, run_id: int):
    run = get_object_or_404(PayrollRun, id=run_id)
    payslips = Payslip.objects.filter(payroll_run=run).select_related(
        "employee", "employee__user"
    )
    totals = payslips.aggregate(
        gross=models.Sum("gross_pay"),
        net=models.Sum("net_pay"),
        taxes=models.Sum("tax_amount"),
    )
    return render(
        request,
        "payroll/run_detail.html",
        {
            "run": run,
            "payslips": payslips,
            "totals": totals,
        },
    )


@require_permission("payroll.manage")
def generate_run(request: HttpRequest, run_id: int):
    run = get_object_or_404(PayrollRun, id=run_id)
    if run.status == PayrollRun.Status.PAID:
        messages.error(request, "This payroll run is already paid.")
        return redirect("payroll:run_detail", run_id=run.id)

    generate_payslips(run)
    messages.success(request, "Payslips generated.")
    return redirect("payroll:run_detail", run_id=run.id)


@require_permission("payroll.manage")
@require_POST
def mark_run_paid(request: HttpRequest, run_id: int):
    """Mark a processed payroll run PAID (freezes it from regeneration)."""
    run = get_object_or_404(PayrollRun, id=run_id)
    if run.status == PayrollRun.Status.PAID:
        messages.info(request, "This payroll run is already marked paid.")
        return redirect("payroll:run_detail", run_id=run.id)
    try:
        mark_payroll_run_paid(run, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc) or "Generate payslips before marking paid.")
        return redirect("payroll:run_detail", run_id=run.id)
    messages.success(request, "Payroll run marked paid and payslips locked.")
    return redirect("payroll:run_detail", run_id=run.id)


@require_permission("payroll.manage")
@require_POST
def review_run(request: HttpRequest, run_id: int):
    """Advance a processed payroll run to REVIEWED (approval-FSM step 1)."""
    run = get_object_or_404(PayrollRun, id=run_id)
    try:
        review_payroll_run(run, actor=request.user, notes=(request.POST.get("notes") or "").strip())
    except ValueError as exc:
        messages.error(request, str(exc) or "This run cannot be reviewed.")
        return redirect("payroll:run_detail", run_id=run.id)
    messages.success(request, "Payroll run marked reviewed.")
    return redirect("payroll:run_detail", run_id=run.id)


@require_permission("payroll.manage")
@require_POST
def approve_run(request: HttpRequest, run_id: int):
    """Approve a reviewed payroll run (records who signed off) — the gate for payment."""
    run = get_object_or_404(PayrollRun, id=run_id)
    try:
        approve_payroll_run(run, actor=request.user, notes=(request.POST.get("notes") or "").strip())
    except ValueError as exc:
        messages.error(request, str(exc) or "This run cannot be approved.")
        return redirect("payroll:run_detail", run_id=run.id)
    messages.success(request, "Payroll run approved and ready to pay.")
    return redirect("payroll:run_detail", run_id=run.id)


@login_required
def payslip_pdf(request: HttpRequest, payslip_id: int):
    """Download a single payslip as a branded PDF (WeasyPrint).

    Access: the payslip's OWN employee, or a payroll.manage user (HR/admin). Payroll is
    a schema-isolated tenant app so the bare pk is already tenant-scoped; this adds the
    within-tenant own-or-manage check so one employee cannot pull a colleague's slip.
    Gracefully degrades if WeasyPrint system libs are missing (RuntimeError) rather than
    500-ing.
    """
    from apps.accounts.decorators import user_has_permission
    from apps.reports.weasy import render_pdf

    payslip = get_object_or_404(
        Payslip.objects.select_related("payroll_run__profile", "employee__user"),
        id=payslip_id,
    )
    emp = _employee_for_user(request.user)
    own = emp is not None and payslip.employee_id == emp.id
    if not own and not user_has_permission(
        request.user, getattr(request, "school", None), ("payroll.manage",)
    ):
        return HttpResponseForbidden("You may not download this payslip.")
    filename = f"payslip-{payslip.reference or payslip.pk}.pdf"
    try:
        return render_pdf(
            request, "payroll/payslip_pdf.html", {"payslip": payslip}, filename=filename
        )
    except RuntimeError as exc:
        messages.error(request, str(exc) or "PDF rendering is unavailable on this server.")
        return redirect("payroll:employee_payslips")


@login_required
def employee_payslips(request: HttpRequest):
    """Payslips for the current user only (user-centric HR)."""
    employee = _employee_for_user(request.user)
    if not employee:
        return HttpResponseForbidden("No payroll profile configured.")

    slips = Payslip.objects.filter(employee=employee).select_related("payroll_run")
    return render(
        request,
        "payroll/employee_payslips.html",
        {
            "employee": employee,
            "payslips": slips.order_by("-payroll_run__period_start"),
        },
    )


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
    return render(
        request,
        "payroll/employee_leave.html",
        {
            "employee": employee,
            "form": form,
            "leaves": leaves,
        },
    )


@require_permission("payroll.manage")
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

    return render(
        request,
        "payroll/create_run.html",
        {
            "profile": profile,
            "today": timezone.now().date(),
        },
    )
