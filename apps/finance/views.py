from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import models
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.siteconfig.models import SiteSettings

from .models import ComplianceProfile, FeePlan, Invoice, LedgerAccount, Payment
from .services import create_fee_invoices


def _active_profile() -> ComplianceProfile | None:
    site = SiteSettings.get_solo()
    if getattr(site, "compliance_profile", None):
        return site.compliance_profile
    return ComplianceProfile.objects.filter(is_active=True).first()


@staff_member_required
def dashboard(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    invoices = Invoice.objects.filter(profile=profile).order_by("-issued_date")[:10]
    payments = Payment.objects.filter(invoice__profile=profile).order_by("-paid_at")[:10]

    total_receivables = (
        Invoice.objects.filter(profile=profile, invoice_type=Invoice.InvoiceType.AR)
        .aggregate(total=models.Sum("balance_amount"))
        .get("total")
        or Decimal("0.00")
    )
    total_payables = (
        Invoice.objects.filter(profile=profile, invoice_type=Invoice.InvoiceType.AP)
        .aggregate(total=models.Sum("balance_amount"))
        .get("total")
        or Decimal("0.00")
    )

    return render(request, "finance/dashboard.html", {
        "profile": profile,
        "invoices": invoices,
        "payments": payments,
        "total_receivables": total_receivables,
        "total_payables": total_payables,
    })


@staff_member_required
def invoice_list(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    status = request.GET.get("status")
    year_id = request.GET.get("year")
    qs = Invoice.objects.filter(profile=profile).select_related("student", "academic_year")

    if status:
        qs = qs.filter(status=status)
    if year_id:
        qs = qs.filter(academic_year_id=year_id)

    return render(request, "finance/invoices.html", {
        "invoices": qs.order_by("-issued_date"),
        "statuses": Invoice.Status.choices,
        "selected_status": status or "",
        "years": AcademicYear.objects.order_by("-start_date"),
        "selected_year": year_id or "",
    })


@staff_member_required
def payment_list(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    qs = Payment.objects.filter(invoice__profile=profile).select_related("invoice", "invoice__student")
    return render(request, "finance/payments.html", {
        "payments": qs.order_by("-paid_at"),
    })


@staff_member_required
def generate_fees(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    plans = FeePlan.objects.filter(is_active=True).select_related("academic_year", "classroom", "specialty")

    if request.method == "POST":
        plan_id = request.POST.get("plan_id")
        if not plan_id:
            messages.error(request, "Please select a fee plan.")
            return redirect("finance:generate_fees")

        plan = get_object_or_404(FeePlan, id=plan_id)
        issued_date = timezone.now().date()
        invoices = create_fee_invoices(plan=plan, profile=profile, issued_date=issued_date)
        messages.success(request, f"Generated {len(invoices)} invoices.")
        return redirect("finance:invoices")

    return render(request, "finance/generate_fees.html", {
        "plans": plans,
    })


@staff_member_required
def trial_balance(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    start = request.GET.get("start")
    end = request.GET.get("end")

    line_filter = models.Q(lines__entry__profile=profile, lines__entry__posted_at__isnull=False)
    if start:
        line_filter &= models.Q(lines__entry__entry_date__gte=start)
    if end:
        line_filter &= models.Q(lines__entry__entry_date__lte=end)

    accounts = LedgerAccount.objects.filter(profile=profile, is_active=True).annotate(
        debit_total=Coalesce(models.Sum("lines__debit", filter=line_filter), Decimal("0.00")),
        credit_total=Coalesce(models.Sum("lines__credit", filter=line_filter), Decimal("0.00")),
    ).order_by("code")

    accounts = list(accounts)
    total_debit = sum((acc.debit_total for acc in accounts), Decimal("0.00"))
    total_credit = sum((acc.credit_total for acc in accounts), Decimal("0.00"))

    return render(request, "finance/trial_balance.html", {
        "profile": profile,
        "accounts": accounts,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "start": start or "",
        "end": end or "",
    })
