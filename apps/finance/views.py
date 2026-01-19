from __future__ import annotations

import json
from calendar import monthrange
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import models
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from django.template.loader import render_to_string

from apps.academics.models import AcademicYear
from apps.payroll.models import Payslip
from apps.siteconfig.models import SiteSettings

from .forms import ReportRequestForm
from .models import (
    ComplianceProfile,
    FeePlan,
    Invoice,
    LedgerAccount,
    Notification,
    Payment,
    PaymentMethod,
    ReportRequest,
)
from .services import (
    PROVIDER_SLUG_TO_METHOD,
    create_fee_invoices,
    finance_dashboard_data,
    generate_payment_link,
    get_payment_integration_by_slug,
    record_provider_payment,
    verify_payment_signature,
)


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

    dashboard_data = finance_dashboard_data(profile)
    return render(request, "finance/dashboard.html", {
        "profile": profile,
        **dashboard_data,
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


@staff_member_required
def invoice_detail(request: HttpRequest, invoice_id: int):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    invoice = get_object_or_404(
        Invoice.objects.select_related("student", "academic_year", "counterparty"),
        id=invoice_id,
        profile=profile,
    )
    payment_link = generate_payment_link(invoice)
    reminder = getattr(invoice, "reminder", None)

    return render(request, "finance/invoice_detail.html", {
        "invoice": invoice,
        "payment_link": payment_link,
        "reminder": reminder,
    })


@staff_member_required
def invoice_receipt(request: HttpRequest, invoice_id: int, payment_id: int | None = None):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    invoice = get_object_or_404(Invoice, id=invoice_id, profile=profile)
    if payment_id:
        payment = get_object_or_404(Payment, id=payment_id, invoice=invoice)
    else:
        payment = invoice.payments.order_by("-paid_at").first()

    if not payment:
        return HttpResponseForbidden("No payment available for this invoice.")

    try:
        from weasyprint import HTML
    except ImportError:
        return HttpResponse("PDF support unavailable (missing WeasyPrint).", status=503)

    context = {
        "invoice": invoice,
        "payment": payment,
        "school": profile.name,
    }
    html = render_to_string("finance/receipt.html", context)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="receipt-{payment.id}.pdf"'
    return response


@csrf_exempt
def payment_provider_webhook(request: HttpRequest, provider_slug: str):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    integration = get_payment_integration_by_slug(provider_slug)
    if not integration:
        return HttpResponseForbidden("Unknown provider.")

    try:
        data = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON payload.")

    signature_header = integration.config.get("signature_header", "X-Signature")
    signature = (
        request.headers.get(signature_header)
        or request.META.get(f"HTTP_{signature_header.upper().replace('-', '_')}")
    )

    if not verify_payment_signature(integration, data, signature):
        return HttpResponseForbidden("Invalid signature.")

    invoice_id = data.get("invoice_id") or data.get("invoice")
    amount = data.get("amount")
    reference = data.get("reference") or data.get("payment_reference")
    external_ref = data.get("external_reference") or reference
    method = data.get("method") or PROVIDER_SLUG_TO_METHOD.get(provider_slug)

    if not invoice_id or amount is None:
        return HttpResponseBadRequest("Missing invoice_id or amount.")

    invoice = Invoice.objects.filter(id=invoice_id).first()
    if not invoice:
        return HttpResponseBadRequest("Invoice not found.")

    payment = record_provider_payment(
        invoice=invoice,
        amount=amount,
        method=method or PaymentMethod.MTN_MOMO,
        reference=reference,
        external_reference=external_ref,
    )

    if not payment:
        return JsonResponse({"status": "ignored"})

    return JsonResponse({"status": "ok", "payment_id": payment.id})


@staff_member_required
def finance_reports(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    today = timezone.localdate()
    arrears_qs = Invoice.objects.filter(
        profile=profile,
        balance_amount__gt=0,
        due_date__lt=today,
    ).select_related("student__classroom", "student__specialty")

    overdue_by_class = arrears_qs.values(
        "student__classroom__name"
    ).annotate(overdue_total=Sum("balance_amount"))

    total_ar = Invoice.objects.filter(profile=profile, invoice_type=Invoice.InvoiceType.AR).aggregate(
        total=Sum("total_amount"),
        balance=Sum("balance_amount"),
    )
    paid_total = Invoice.objects.filter(
        profile=profile,
        invoice_type=Invoice.InvoiceType.AR,
        status=Invoice.Status.PAID,
    ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    issued_total = total_ar.get("total") or Decimal("0.00")
    collection_rate = (paid_total / issued_total * 100) if issued_total else Decimal("0.00")

    payroll_liabilities = Payslip.objects.filter(
        payroll_run__profile=profile
    ).aggregate(
        total_taxes=Sum("tax_amount"),
        total_employee=Sum("employee_contributions"),
        total_employer=Sum("employer_contributions"),
    )

    report_form = ReportRequestForm()

    return render(request, "finance/reports.html", {
        "profile": profile,
        "overdue": overdue_by_class,
        "collection_rate": collection_rate,
        "liabilities": payroll_liabilities,
        "report_form": report_form,
    })


@staff_member_required
def submit_report_request(request: HttpRequest):
    profile = _active_profile()
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
            created_by=request.user,
        )
        messages.success(request, "Report request logged. We will notify you once ready.")
        return redirect("finance:reports")

    messages.error(request, "Please fix the errors below.")
    return render(request, "finance/reports.html", {
        "profile": profile,
        "overdue": [],
        "collection_rate": Decimal("0.00"),
        "liabilities": {},
        "report_form": form,
    })


@staff_member_required
def notifications(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    alerts = Notification.objects.order_by("-created_at")[:25]
    return render(request, "finance/notifications.html", {
        "alerts": alerts,
    })
