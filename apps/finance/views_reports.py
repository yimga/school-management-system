"""
Finance reports views (2.1 giant-file decomposition).
Re-exported from views.py for URL wiring.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import Sum

from apps.payroll.models import Payslip

from .forms import ReportRequestForm
from .models import Invoice, Notification
from .ohada_reports import build_dsf_report


def _active_profile(request: HttpRequest | None = None):
    """Resolve active compliance profile for reports (shared helper)."""
    from apps.platform_runtime.helpers import get_effective_site_settings
    from .models import ComplianceProfile

    site = get_effective_site_settings(request=request)
    if getattr(site, "compliance_profile", None):
        return site.compliance_profile
    return ComplianceProfile.objects.filter(is_active=True).first()


@staff_member_required(login_url=settings.LOGIN_URL)
def finance_reports(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")
    start = parse_date(request.GET.get("start") or "")
    end = parse_date(request.GET.get("end") or "")

    today = timezone.localdate()
    arrears_qs = Invoice.objects.filter(
        profile=profile,
        balance_amount__gt=0,
        due_date__lt=today,
    ).select_related("student__classroom", "student__specialty")

    overdue_by_class = arrears_qs.values("student__classroom__name").annotate(
        overdue_total=Sum("balance_amount")
    )

    total_ar = Invoice.objects.filter(
        profile=profile, invoice_type=Invoice.InvoiceType.AR
    ).aggregate(
        total=Sum("total_amount"),
        balance=Sum("balance_amount"),
    )
    paid_total = Invoice.objects.filter(
        profile=profile,
        invoice_type=Invoice.InvoiceType.AR,
        status=Invoice.Status.PAID,
    ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    issued_total = total_ar.get("total") or Decimal("0.00")
    collection_rate = (
        (paid_total / issued_total * 100) if issued_total else Decimal("0.00")
    )

    payroll_liabilities = Payslip.objects.filter(
        payroll_run__profile=profile
    ).aggregate(
        total_taxes=Sum("tax_amount"),
        total_employee=Sum("employee_contributions"),
        total_employer=Sum("employer_contributions"),
    )

    report_form = ReportRequestForm()
    dsf_report = build_dsf_report(profile=profile, start_date=start, end_date=end)

    return render(
        request,
        "finance/reports.html",
        {
            "profile": profile,
            "overdue": overdue_by_class,
            "collection_rate": collection_rate,
            "liabilities": payroll_liabilities,
            "report_form": report_form,
            "dsf_report": dsf_report,
            "report_start": start,
            "report_end": end,
            "page_title": "Finance Intelligence",
            "page_subtitle": "Reports, overdue insights, payroll liabilities, and OHADA/DSF summary.",
            "action_url": reverse("finance:dashboard"),
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def submit_report_request(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    if request.method != "POST":
        return redirect("finance:reports")

    form = ReportRequestForm(request.POST)
    if form.is_valid():
        report = form.save(commit=False)
        report.requested_by = request.user
        report.save()
        Notification.objects.create(
            title="Report request received",
            message=f"{request.user.get_full_name()} requested {report.get_report_type_display()}",
            severity=Notification.Severity.INFO,
            recipient=request.user,
            created_by=request.user,
        )
        messages.success(
            request, "Report request logged. We will notify you once ready."
        )
        return redirect("finance:reports")

    messages.error(request, "Please fix the errors below.")
    dsf_report = build_dsf_report(profile=profile, start_date=None, end_date=None)
    return render(
        request,
        "finance/reports.html",
        {
            "profile": profile,
            "overdue": [],
            "collection_rate": Decimal("0.00"),
            "liabilities": {},
            "report_form": form,
            "report_start": None,
            "report_end": None,
            "dsf_report": dsf_report,
            "page_title": "Finance Intelligence",
            "page_subtitle": "Reports, overdue insights, payroll liabilities, and OHADA/DSF summary.",
            "action_url": reverse("finance:dashboard"),
        },
    )
