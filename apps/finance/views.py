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
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from django.template.loader import render_to_string

try:
    from django.http import HttpResponseTooManyRequests
except ImportError:
    class HttpResponseTooManyRequests(HttpResponse):
        status_code = 429

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
from .webhook_security import (
    check_webhook_ip_whitelist,
    check_webhook_rate_limit,
    compute_idempotency_key,
    check_webhook_idempotency,
    log_webhook_request,
    IPWhitelistViolation,
    RateLimitExceeded,
    IdempotencyViolation,
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
    summary = dashboard_data.get("summary", {})
    hero = {
        "tagline": "Finance Dashboard",
        "title": profile.name,
        "subtitle": "Receivables, collections, and alerts",
        "icon": "bi-cash-coin",
        "stats": [
            {"label": "Receivables", "value": summary.get("receivables"), "meta": "Outstanding AR"},
            {"label": "Collected", "value": summary.get("paid"), "meta": "YTD payments"},
            {"label": "Overdue", "value": summary.get("overdue"), "meta": "Invoices late"},
        ],
        "actions": [
            {"label": "All Invoices", "url": "/finance/invoices/"},
            {"label": "Payments", "url": "/finance/payments/"},
        ],
    }
    return render(request, "finance/dashboard.html", {
        "profile": profile,
        "hero": hero,
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

    paginator = Paginator(qs.order_by("-issued_date"), 25)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    return render(request, "finance/invoices.html", {
        "invoices": page_obj,
        "statuses": Invoice.Status.choices,
        "selected_status": status or "",
        "years": AcademicYear.objects.order_by("-start_date"),
        "selected_year": year_id or "",
        "page_obj": page_obj,
        "paginator": paginator,
    })


@staff_member_required
def payment_list(request: HttpRequest):
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    qs = Payment.objects.filter(invoice__profile=profile).select_related(
        "invoice",
        "invoice__student",
        "invoice__academic_year",
    )
    paginator = Paginator(qs.order_by("-paid_at"), 25)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    return render(request, "finance/payments.html", {
        "payments": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
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
    if request.method == "POST" and request.FILES.get("attachment"):
        invoice.attachment = request.FILES["attachment"]
        invoice.save(update_fields=["attachment"])
        messages.success(request, "Attachment uploaded.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

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
    """
    Webhook endpoint for payment provider callbacks.
    
    SECURITY: This endpoint is CSRF-exempt to allow external payment providers
    to send notifications. We protect it with:
    1. IP whitelist verification (must be in integration config)
    2. Rate limiting per provider
    3. Signature verification from integration
    4. Idempotency checks to prevent duplicate processing
    5. Full request logging for audit trail
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    integration = get_payment_integration_by_slug(provider_slug)
    if not integration:
        log_webhook_request(request, provider_slug, None, None, "rejected", "Unknown provider")
        return HttpResponseForbidden("Unknown provider.")

    # SECURITY CHECK 1: Verify IP is whitelisted
    try:
        check_webhook_ip_whitelist(request, integration, provider_slug)
    except IPWhitelistViolation as e:
        return HttpResponseForbidden(str(e))

    # SECURITY CHECK 2: Check rate limiting
    try:
        check_webhook_rate_limit(integration, provider_slug)
    except RateLimitExceeded as e:
        return HttpResponseTooManyRequests(str(e))

    try:
        data = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        log_webhook_request(request, provider_slug, None, None, "rejected", "Invalid JSON")
        return HttpResponseBadRequest("Invalid JSON payload.")

    invoice_id = data.get("invoice_id") or data.get("invoice")
    amount = data.get("amount")
    reference = data.get("reference") or data.get("payment_reference")
    external_ref = data.get("external_reference") or reference

    log_webhook_request(
        request,
        provider_slug,
        invoice_id,
        amount,
        "received",
    )

    # SECURITY CHECK 3: Verify signature
    signature_header = integration.config.get("signature_header", "X-Signature")
    signature = (
        request.headers.get(signature_header)
        or request.META.get(f"HTTP_{signature_header.upper().replace('-', '_')}")
    )

    if not verify_payment_signature(integration, data, signature):
        log_webhook_request(
            request,
            provider_slug,
            invoice_id,
            amount,
            "rejected",
            "Invalid signature",
        )
        return HttpResponseForbidden("Invalid signature.")

    if not invoice_id or amount is None:
        log_webhook_request(
            request,
            provider_slug,
            invoice_id,
            amount,
            "rejected",
            "Missing invoice_id or amount",
        )
        return HttpResponseBadRequest("Missing invoice_id or amount.")

    # SECURITY CHECK 4: Check idempotency to prevent duplicate payments
    idempotency_key = compute_idempotency_key(
        invoice_id,
        amount,
        provider_slug,
        external_ref,
    )
    
    if check_webhook_idempotency(idempotency_key):
        log_webhook_request(
            request,
            provider_slug,
            invoice_id,
            amount,
            "duplicate",
            "Idempotency key already processed",
        )
        # Return success to acknowledge duplicate (provider doesn't retry)
        return JsonResponse({"status": "duplicate", "message": "Already processed"})

    invoice = Invoice.objects.filter(id=invoice_id).first()
    if not invoice:
        log_webhook_request(
            request,
            provider_slug,
            invoice_id,
            amount,
            "rejected",
            "Invoice not found",
        )
        return HttpResponseBadRequest("Invoice not found.")

    method = data.get("method") or PROVIDER_SLUG_TO_METHOD.get(provider_slug)
    payment = record_provider_payment(
        invoice=invoice,
        amount=amount,
        method=method or PaymentMethod.MTN_MOMO,
        reference=reference,
        external_reference=external_ref,
    )

    if not payment:
        log_webhook_request(
            request,
            provider_slug,
            invoice_id,
            amount,
            "ignored",
            "Payment not recorded",
        )
        return JsonResponse({"status": "ignored"})

    log_webhook_request(
        request,
        provider_slug,
        invoice_id,
        amount,
        "completed",
    )
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
