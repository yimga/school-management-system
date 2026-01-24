from __future__ import annotations

import json
import logging
from calendar import monthrange
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
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
from django.views.decorators.http import require_http_methods

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
    WebhookLog,
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
from .security import (
    PaymentValidator,
    WebhookSecurityValidator,
    webhook_security_required,
)

logger = logging.getLogger(__name__)


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


@login_required
def invoice_list(request: HttpRequest):
    """
    Invoice list view with role-based filtering.
    Staff see all invoices; parents see only their children's invoices.
    """
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian
    
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    status = request.GET.get("status")
    year_id = request.GET.get("year")
    qs = Invoice.objects.filter(profile=profile).select_related("student", "academic_year")
    
    # Filter invoices based on user role
    if request.user.role == User.Role.PARENT:
        # Parents can only see invoices for their children
        parent_students = StudentGuardian.objects.filter(
            guardian_user=request.user
        ).values_list('student_id', flat=True)
        qs = qs.filter(student_id__in=parent_students)
    elif not (request.user.is_staff or request.user.is_superuser or request.user.role == User.Role.ADMIN):
        return HttpResponseForbidden("You don't have permission to view invoices.")
    
    # Continue with existing filtering logic

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


@login_required
def invoice_detail(request: HttpRequest, invoice_id: int):
    """
    Invoice detail view with object-level permission check.
    Staff can view all invoices; parents can only view their children's invoices.
    """
    from apps.accounts.permissions import can_view_invoice

    if not can_view_invoice(request.user, invoice_id):
        return HttpResponseForbidden("You don't have permission to view this invoice.")
    
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
@require_http_methods(["POST"])
def payment_provider_webhook(request: HttpRequest, provider_slug: str):
    """
    Secure webhook endpoint for payment provider callbacks.
    
    Security checks (in order):
    1. HTTP method validation (POST only)
    2. Provider validation
    3. IP whitelist check
    4. Rate limiting
    5. HMAC signature verification
    6. Idempotency check
    7. Payment data validation
    8. Transaction integrity
    
    Audit: All attempts logged to WebhookLog for compliance.
    
    Args:
        request: HTTP request with payment data
        provider_slug: Payment provider code (e.g., 'mtn_momo', 'orange_money')
        
    Returns:
        JsonResponse with status and payment_id on success
        HttpResponseForbidden/HttpResponseBadRequest on validation failure
    """
    
    integration = get_payment_integration_by_slug(provider_slug)
    if not integration:
        logger.warning(f"Webhook request for unknown provider: {provider_slug}")
        return HttpResponseForbidden("Unknown provider.")

    try:
        request_body = request.body
        data = json.loads(request_body.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Invalid webhook payload from {provider_slug}: {e}")
        WebhookLog.objects.create(
            provider=provider_slug,
            reference_id="unknown",
            client_ip=WebhookSecurityValidator.get_client_ip(request),
            status=WebhookLog.Status.INVALID,
            error_message=f"Invalid JSON: {str(e)}",
        )
        return HttpResponseBadRequest("Invalid JSON payload.")

    # Initialize security validator
    validator = WebhookSecurityValidator(integration.config or {})
    client_ip = validator.get_client_ip(request)
    reference_id = data.get("reference") or data.get("payment_reference") or "unknown"

    # Step 1: IP whitelist check
    if not validator.validate_ip_whitelist(client_ip):
        WebhookLog.objects.create(
            provider=provider_slug,
            reference_id=reference_id,
            client_ip=client_ip,
            status=WebhookLog.Status.INVALID,
            error_message=f"IP not whitelisted: {client_ip}",
        )
        logger.warning(f"Rejected webhook from unauthorized IP {client_ip} for {provider_slug}")
        return HttpResponseForbidden("IP not whitelisted.")

    # Step 2: Rate limiting check
    if not validator.validate_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP {client_ip}")
        return HttpResponseForbidden("Rate limit exceeded.")

    # Step 3: Signature verification
    signature_header = integration.config.get("signature_header", "X-Signature") if integration.config else "X-Signature"
    signature = (
        request.headers.get(signature_header)
        or request.META.get(f"HTTP_{signature_header.upper().replace('-', '_')}")
    )

    signature_valid = validator.validate_signature(request_body, signature or "")
    if not signature_valid:
        WebhookLog.objects.create(
            provider=provider_slug,
            reference_id=reference_id,
            client_ip=client_ip,
            signature_valid=False,
            status=WebhookLog.Status.INVALID,
            error_message="Invalid HMAC signature",
            request_body=request_body.decode()[:500],  # Store first 500 chars
        )
        logger.warning(f"Invalid signature from {provider_slug} ({client_ip})")
        return HttpResponseForbidden("Invalid signature.")

    # Step 4: Idempotency check (prevent duplicate payments)
    if not validator.validate_idempotency(provider_slug, reference_id):
        webhook_log = WebhookLog.objects.create(
            provider=provider_slug,
            reference_id=reference_id,
            client_ip=client_ip,
            signature_valid=True,
            status=WebhookLog.Status.DUPLICATE,
            request_body=request_body.decode()[:500],
        )
        logger.info(f"Duplicate webhook from {provider_slug}: {reference_id}")
        return JsonResponse({"status": "ignored", "reason": "duplicate"})

    # Step 5: Extract and validate payment data
    invoice_id = data.get("invoice_id") or data.get("invoice")
    amount = data.get("amount")
    method = data.get("method") or PROVIDER_SLUG_TO_METHOD.get(provider_slug)

    # Validate amount
    is_valid, error_msg = PaymentValidator.validate_amount(amount)
    if not is_valid:
        WebhookLog.objects.create(
            provider=provider_slug,
            reference_id=reference_id,
            client_ip=client_ip,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            error_message=f"Invalid amount: {error_msg}",
            request_body=request_body.decode()[:500],
        )
        logger.warning(f"Invalid payment amount from {provider_slug}: {amount}")
        return HttpResponseBadRequest(error_msg)

    if not invoice_id:
        WebhookLog.objects.create(
            provider=provider_slug,
            reference_id=reference_id,
            client_ip=client_ip,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            error_message="Missing invoice_id in payload",
            request_body=request_body.decode()[:500],
        )
        return HttpResponseBadRequest("Missing invoice_id.")

    # Step 6: Fetch invoice
    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        WebhookLog.objects.create(
            provider=provider_slug,
            reference_id=reference_id,
            client_ip=client_ip,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            error_message=f"Invoice {invoice_id} not found",
        )
        logger.warning(f"Invoice {invoice_id} not found from webhook {provider_slug}")
        return HttpResponseBadRequest(f"Invoice {invoice_id} not found.")

    # Step 7: Validate amount against invoice balance
    invoice_paid = sum(invoice.payments.values_list("amount", flat=True)) or Decimal("0")
    is_valid, error_msg = PaymentValidator.validate_against_invoice(
        Decimal(str(amount)),
        invoice.total_amount,
        invoice_paid,
    )
    if not is_valid:
        WebhookLog.objects.create(
            provider=provider_slug,
            reference_id=reference_id,
            client_ip=client_ip,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            invoice=invoice,
            error_message=f"Amount validation failed: {error_msg}",
        )
        logger.warning(f"Payment amount validation failed for invoice {invoice_id}: {error_msg}")
        return HttpResponseBadRequest(error_msg)

    # Step 8: Record payment within transaction (atomic)
    try:
        with transaction.atomic():
            # Create WebhookLog first (in PROCESSING state)
            webhook_log = WebhookLog.objects.create(
                provider=provider_slug,
                reference_id=reference_id,
                client_ip=client_ip,
                signature_valid=True,
                status=WebhookLog.Status.PROCESSING,
                invoice=invoice,
                request_body=request_body.decode()[:500],
            )

            # Record the payment
            payment = record_provider_payment(
                invoice=invoice,
                amount=amount,
                method=method or PaymentMethod.MTN_MOMO,
                reference=data.get("reference", ""),
                external_reference=reference_id,
            )

            if not payment:
                webhook_log.status = WebhookLog.Status.FAILED
                webhook_log.error_message = "Failed to create payment record"
                webhook_log.save(update_fields=["status", "error_message"])
                logger.error(f"Failed to record payment for webhook {reference_id}")
                return JsonResponse({"status": "error", "reason": "payment_creation_failed"})

            # Mark webhook as successfully processed
            webhook_log.payment = payment
            webhook_log.status = WebhookLog.Status.PROCESSED
            webhook_log.response_status = 200
            webhook_log.save(update_fields=["payment", "status", "response_status"])

            logger.info(
                f"Successfully processed webhook from {provider_slug}: "
                f"Invoice {invoice_id}, Payment {payment.id}, Amount {amount} {provider_slug.upper()}"
            )

            return JsonResponse({
                "status": "ok",
                "payment_id": payment.id,
                "reference": reference_id,
            })

    except Exception as e:
        # Handle any transaction errors
        logger.exception(f"Transaction error processing webhook {reference_id}: {e}")
        try:
            webhook_log = WebhookLog.objects.get(reference_id=reference_id, provider=provider_slug)
            webhook_log.status = WebhookLog.Status.FAILED
            webhook_log.error_message = f"Transaction error: {str(e)[:200]}"
            webhook_log.save(update_fields=["status", "error_message"])
        except WebhookLog.DoesNotExist:
            WebhookLog.objects.create(
                provider=provider_slug,
                reference_id=reference_id,
                client_ip=client_ip,
                signature_valid=True,
                status=WebhookLog.Status.FAILED,
                error_message=f"Transaction error: {str(e)[:200]}",
            )
        return JsonResponse({"status": "error", "reason": "processing_failed"}, status=500)


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
            recipient=request.user,
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

    alerts = Notification.objects.filter(
        models.Q(recipient=request.user) | models.Q(created_by=request.user)
    ).order_by("-created_at")[:25]
    return render(request, "finance/notifications.html", {
        "alerts": alerts,
    })
