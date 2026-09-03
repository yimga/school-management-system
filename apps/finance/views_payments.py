"""
Finance payment and webhook views (§6.15 app-by-app split — subdomain: payments).

Payment list, cash office closure, split allocation, scan/teller placeholder,
and payment provider webhook. Single place for payment-related UI and webhook flows.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from apps.accounts.decorators import require_permission
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.academics.models import AcademicYear
from apps.platform_runtime.config_resolver import get_effective_config
from apps.siteconfig.config_service import get_effective_flags

from .forms import CashOfficeClosureForm, SplitAllocationForm, TellerScanForm
from .models import (
    CashOfficeClosure,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
    SuspensePayment,
    WebhookLog,
)
from .services import (
    apply_payment,
    assign_invoice_payer_shares,
    get_payment_integration_by_slug,
    normalize_provider_slug,
    record_provider_payment,
    split_amount_equally,
    PROVIDER_SLUG_TO_METHOD,
)
from .security import PaymentValidator, WebhookSecurityValidator
from .receipt_verification import ReceiptVerificationService
from .ocr_runtime import get_ocr_runtime_status
from .views_common import (
    FINANCE_SOFT_FAILURES,
    _active_profile,
    _backend_flags,
    finance_detail_redirect,
    finance_save_redirect,
)

logger = logging.getLogger(__name__)


@require_permission("finance.view", "finance.manage")
def payment_list(request: HttpRequest):
    # profile is a ComplianceProfile (country_code, no school column), so
    # filter(invoice__profile=...) alone bounds this to a COUNTRY.
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("Open from a school (tenant) workspace.")

    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    # Scoped through the INVOICE's school rather than Payment.school: both
    # columns are nullable, but migration 0082 backfilled Invoice.school for
    # every AR row with a student, and nothing backfilled Payment.school -- so
    # keying on the payment's own column would hide a school's legacy receipts
    # from its own list.
    qs = Payment.objects.filter(
        invoice__school=school, invoice__profile=profile
    ).select_related(
        "invoice", "invoice__student", "invoice__academic_year"
    )

    method = (request.GET.get("method") or "").strip()
    if method and method in [c[0] for c in PaymentMethodCode.choices]:
        qs = qs.filter(method=method)
    date_from = parse_date(request.GET.get("date_from") or "")
    date_to = parse_date(request.GET.get("date_to") or "")
    if date_from:
        qs = qs.filter(paid_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(paid_at__date__lte=date_to)

    _payment_order_map = {
        "paid_at": "paid_at",
        "-paid_at": "-paid_at",
        "amount": "amount",
        "-amount": "-amount",
    }
    order_param = (request.GET.get("order") or "").strip()
    order_by = _payment_order_map.get(order_param, "-paid_at")
    ordered_qs = qs.order_by(order_by)

    if request.GET.get("export") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Invoice", "Method", "Amount", "Paid at", "Student", "Receipt"])
        for pay in ordered_qs[:5000]:
            inv = pay.invoice
            w.writerow(
                [
                    inv.reference or str(inv.id),
                    pay.get_method_display(),
                    str(pay.amount),
                    pay.paid_at.isoformat() if pay.paid_at else "",
                    str(inv.student) if inv.student_id else "",
                    pay.receipt_number or "",
                ]
            )
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="payments_export.csv"'
        return resp

    if request.GET.get("export") == "pdf":
        try:
            from weasyprint import HTML
        except ImportError:
            return HttpResponse("PDF export requires WeasyPrint.", status=503)

        def _d(d):
            return d.strftime("%Y-%m-%d %H:%M") if d else ""

        rows_html = "".join(
            f"<tr><td>{pay.invoice.reference or pay.invoice_id}</td><td>{pay.get_method_display()}</td>"
            f"<td>{pay.amount}</td><td>{_d(pay.paid_at)}</td><td>{pay.invoice.student or ''}</td>"
            f"<td>{pay.receipt_number or ''}</td></tr>"
            for pay in ordered_qs[:500]
        )
        title = get_effective_config(key="site_name", request=request) or "Payments"
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Payments</title>
<style>body{{font-family:system-ui,sans-serif;font-size:10pt;margin:12mm;}}
table{{width:100%;border-collapse:collapse;}} th,td{{border:1px solid #ddd;padding:6px;text-align:left;}}
th{{background:#f5f5f5;}} .header{{margin-bottom:12px;}}</style></head>
<body><div class="header"><h1>{title}</h1><p>Payments export</p></div>
<table><thead><tr><th>Invoice</th><th>Method</th><th>Amount</th><th>Paid at</th><th>Student</th><th>Receipt</th></tr></thead>
<tbody>{rows_html}</tbody></table></body></html>"""
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = 'attachment; filename="payments_export.pdf"'
        return resp

    paginator = Paginator(ordered_qs, 25)
    page_number = request.GET.get("page") or 1
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()

    flags = get_effective_flags(request)
    enable_ocr_scan_teller = bool(flags.get("enable_ocr_scan_teller"))
    return render(
        request,
        "finance/payments.html",
        {
            "payments": page_obj,
            "page_obj": page_obj,
            "paginator": paginator,
            "pagination_extra_query": pagination_extra_query,
            "enable_ocr_scan_teller": enable_ocr_scan_teller,
            "payment_methods": PaymentMethodCode.choices,
            "selected_method": method or "",
            "date_from": request.GET.get("date_from") or "",
            "date_to": request.GET.get("date_to") or "",
            "page_title": "Payments",
            "page_subtitle": "Incoming and outgoing payments.",
            "action_url": reverse("finance:dashboard"),
            "order_options": [
                ("-paid_at", "Date (newest first)"),
                ("paid_at", "Date (oldest first)"),
                ("-amount", "Amount (high to low)"),
                ("amount", "Amount (low to high)"),
            ],
            "selected_order": order_param or "-paid_at",
        },
    )


@require_permission("finance.manage")
def cash_office_closure(request: HttpRequest):
    """
    Daily cash closure: recomputes cash collected from completed CASH payments
    for the selected day; stores opening cash, deposited amount, physical cash, discrepancy.
    """
    # This reconciles physical cash against recorded takings. Bounded only by
    # ComplianceProfile it summed every co-located school's cash into this
    # school's closure, and the discrepancy it reports is the number someone
    # is held to.
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("Open from a school (tenant) workspace.")

    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    today = timezone.localdate()
    date_param = (request.GET.get("date") or "").strip()
    initial_date = parse_date(date_param) if date_param else today
    form = CashOfficeClosureForm(
        request.POST or None,
        profile=profile,
        initial={"closure_date": initial_date},
    )

    closure_date = initial_date
    if request.method == "POST" and form.is_valid():
        closure_date = form.cleaned_data["closure_date"]
    cash_collected = Payment.objects.filter(
        invoice__school=school,
        invoice__profile=profile,
        method=PaymentMethodCode.CASH,
        status="completed",
        paid_at__date=closure_date,
    ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"] or Decimal(
        "0.00"
    )

    if request.method == "POST":
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked
        if form.is_valid():
            closure, _created = CashOfficeClosure.objects.get_or_create(
                profile=profile,
                closure_date=closure_date,
            )
            closure.opening_cash = form.cleaned_data["opening_cash"]
            closure.cash_collected = cash_collected
            closure.deposited_to_bank = form.cleaned_data["deposited_to_bank"]
            closure.cash_on_hand = form.cleaned_data["cash_on_hand"]
            closure.bank_account = form.cleaned_data["bank_account"]
            closure.deposit_reference = form.cleaned_data["deposit_reference"]
            closure.notes = form.cleaned_data["notes"]
            closure.status = CashOfficeClosure.Status.CLOSED
            closure.closed_by = request.user
            closure.save()
            messages.success(
                request,
                f"Cash closure saved for {closure.closure_date}. "
                f"Expected {closure.expected_cash}, discrepancy {closure.discrepancy}.",
            )
            return finance_save_redirect(request, "finance:cash_office_closure")
        messages.error(request, "Please correct the closure form errors and try again.")

    def _to_decimal_or_zero(raw_value) -> Decimal:
        try:
            return Decimal(str(raw_value).strip() or "0")
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0")

    opening_cash = _to_decimal_or_zero(form["opening_cash"].value())
    deposited_to_bank = _to_decimal_or_zero(form["deposited_to_bank"].value())
    cash_on_hand = _to_decimal_or_zero(form["cash_on_hand"].value())
    expected_cash = opening_cash + cash_collected - deposited_to_bank
    discrepancy_preview = cash_on_hand - expected_cash

    recent_closures = CashOfficeClosure.objects.filter(profile=profile).order_by(
        "-closure_date", "-updated_at"
    )[:10]

    return render(
        request,
        "finance/cash_office_closure.html",
        {
            "form": form,
            "closure_profile_id": profile.pk,
            "cash_collected": cash_collected,
            "expected_cash": expected_cash,
            "discrepancy_preview": discrepancy_preview,
            "recent_closures": recent_closures,
        },
    )


@require_permission("finance.manage")
def split_allocation(request: HttpRequest):
    """
    Record a single payment split across fee types.
    Creates an invoice with multiple lines, one payment for the total, then applies
    payment and posts to OHADA ledger.
    """
    from apps.people.models import StudentGuardian, StudentProfile

    # AcademicYear.is_active is documented on the field itself as "exactly one
    # should be active PER SCHOOL", so an unscoped is_active read does not return
    # "the" active year -- it returns whichever school's year sorts first. On the
    # cloud each tenant has its own schema and that is invisible; on an edge box
    # every school shares one schema, so this page was liable to bill a student
    # against another school's academic year. The school is what bounds it.
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("Open from a school (tenant) workspace.")

    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    active_year = (
        AcademicYear.objects.filter(school=school, is_active=True)
        .order_by("-start_date")
        .first()
    )
    if not active_year:
        return render(
            request,
            "finance/split_allocation.html",
            {
                "form": None,
                "error": "No active academic year. Set an academic year as active first.",
            },
        )
    students = StudentProfile.objects.filter(
        school=school, academic_year=active_year
    ).order_by("last_name", "first_name")
    selected_student_id = (
        request.POST.get("student") or request.GET.get("student") or ""
    ).strip()
    guardians = StudentGuardian.objects.none()
    if selected_student_id.isdigit():
        guardians = StudentGuardian.objects.filter(
            student_id=int(selected_student_id),
            student__school=school,
            student__academic_year=active_year,
            can_view_finance=True,
            guardian_user__is_active=True,
        ).select_related("guardian_user")

    form = SplitAllocationForm(
        request.POST or None,
        student_queryset=students,
        guardian_queryset=guardians,
    )

    if request.method == "POST":
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked

    if request.method == "POST" and form.is_valid():
        student = form.cleaned_data["student"]
        total_amount = form.cleaned_data["total_amount"]
        method = form.cleaned_data["method"]
        split_mode = (form.cleaned_data.get("split_mode") or "none").strip().lower()
        allocations = form.get_allocations()
        today = timezone.now().date()
        short_id = uuid.uuid4().hex[:8].upper()
        reference = f"SPLIT-{student.id}-{today.isoformat()}-{short_id}"
        payer_allocations = []
        if split_mode == "custom":
            payer_allocations = form.get_payer_allocations()
        elif split_mode == "equal":
            student_guardians = list(
                StudentGuardian.objects.filter(  # tenant-isolation-allow: bound to one school-resolved student row; links follow the student (reviewed 2026-09-03)
                    student=student,
                    can_view_finance=True,
                    guardian_user__is_active=True,
                ).select_related("guardian_user")
            )
            equal_parts = split_amount_equally(total_amount, len(student_guardians))
            payer_allocations = list(zip(student_guardians, equal_parts))

        with transaction.atomic():
            invoice = Invoice.objects.create(
                school=school,
                profile=profile,
                academic_year=active_year,
                student=student,
                reference=reference,
                invoice_type=Invoice.InvoiceType.AR,
                issued_date=today,
                due_date=today,
                status=Invoice.Status.ISSUED,
                total_amount=total_amount,
                created_by=request.user,
            )
            for desc, amount in allocations:
                InvoiceLine.objects.create(
                    invoice=invoice,
                    description=desc,
                    quantity=Decimal("1.00"),
                    unit_price=amount,
                    amount=amount,
                )
            if payer_allocations:
                assign_invoice_payer_shares(invoice, payer_allocations, due_date=today)
            payment = Payment.objects.create(
                school=school,
                invoice=invoice,
                student=student,
                amount=total_amount,
                method=method,
                paid_at=timezone.now(),
                created_by=request.user,
            )
            apply_payment(payment)
        messages.success(
            request,
            f"Payment of {total_amount} recorded for {student} (invoice {invoice.reference}).",
        )
        return finance_detail_redirect(request, invoice.id)

    return render(
        request,
        "finance/split_allocation.html",
        {"form": form, "active_year": active_year},
    )


@require_permission("finance.view", "finance.manage")
def scan_teller_placeholder(request: HttpRequest):
    """
    OCR scan helper for physical teller / receipt uploads.
    Extracts amount/reference/date and suggests matching suspense transactions.
    """
    flags = _backend_flags(request)
    if not flags.get("enable_ocr_scan_teller"):
        return HttpResponseForbidden("Scan Teller is disabled in Feature Control.")

    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    verification_method = (
        get_effective_config(
            key="finance_receipt_verification_method",
            request=request,
            default="pattern",
        )
        or "pattern"
    )
    ocr_runtime_status = get_ocr_runtime_status(
        verification_method,
        get_effective_config(key="marksheet_ocr_command", request=request, default=""),
    )
    form = TellerScanForm(request.POST or None, request.FILES or None)

    extraction = None
    match_preview = None
    suspense_matches = []
    invoice_matches = []
    suggested_tolerance = Decimal(
        str(
            get_effective_config(
                key="finance_bank_verification_amount_tolerance",
                request=request,
                default="1.00",
            )
        )
    )

    if request.method == "POST" and form.is_valid():
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked
        if verification_method != "pattern" and not ocr_runtime_status.get(
            "ready", False
        ):
            messages.warning(
                request,
                "OCR runtime is not ready for the selected method. "
                "Extraction may fail until integration credentials/runtime are configured.",
            )
        verifier = ReceiptVerificationService(
            verification_method=verification_method,
            marksheet_ocr_command=get_effective_config(
                key="marksheet_ocr_command", request=request, default=""
            ),
        )
        extraction = verifier.extract_receipt_data(form.cleaned_data["receipt_file"])

        extracted_amount = extraction.get("amount")
        expected_amount = form.cleaned_data.get("expected_amount")
        reference_hint = (form.cleaned_data.get("transaction_reference") or "").strip()
        extracted_reference = extraction.get("reference") or reference_hint

        if extracted_amount is not None and expected_amount is not None:
            amount_diff = abs(extracted_amount - expected_amount)
            match_preview = {
                "matches": amount_diff <= suggested_tolerance,
                "expected_amount": expected_amount,
                "extracted_amount": extracted_amount,
                "difference": amount_diff,
                "tolerance": suggested_tolerance,
            }

        if extracted_amount is not None:
            low = max(Decimal("0.00"), extracted_amount - suggested_tolerance)
            high = extracted_amount + suggested_tolerance

            suspense_matches = list(
                SuspensePayment.objects.filter(
                    status__in=[
                        SuspensePayment.Status.OPEN,
                        SuspensePayment.Status.PARTIAL,
                    ],
                    amount__gte=low,
                    amount__lte=high,
                )
                .select_related("bank_statement_entry", "suggested_student")
                .order_by("-created_at")[:8]
            )

            invoice_qs = Invoice.objects.select_related("student").filter(
                profile=profile,
                status__in=[
                    Invoice.Status.ISSUED,
                    Invoice.Status.PARTIAL,
                    Invoice.Status.OVERDUE,
                ],
                balance_amount__gte=low,
                balance_amount__lte=high,
            )
            if extracted_reference:
                invoice_qs = invoice_qs.filter(
                    Q(reference__icontains=extracted_reference)
                    | Q(payment_code__icontains=extracted_reference)
                )
            invoice_matches = list(invoice_qs.order_by("due_date", "id")[:8])

    return render(
        request,
        "finance/scan_teller_placeholder.html",
        {
            "form": form,
            "verification_method": verification_method,
            "extraction": extraction,
            "match_preview": match_preview,
            "suspense_matches": suspense_matches,
            "invoice_matches": invoice_matches,
            "suggested_tolerance": suggested_tolerance,
            "ocr_runtime_status": ocr_runtime_status,
        },
    )


def _registration_id_for_invoice(invoice):
    """The RESERVED ticket registration this invoice was raised for, if any.

    Matches on registration.metadata['invoice_id'], which
    create_ticket_invoice_for_registration writes, and constrains the event to
    the invoice's school. Returns None on anything unexpected: this runs inside
    a webhook whose posted Payment must never be rolled back by a ticket lookup.
    """
    school_id = getattr(invoice, "school_id", None)
    if school_id is None or getattr(invoice, "pk", None) is None:
        return None
    try:
        from apps.school_events.models import EventRegistration

        # tenant-isolation-allow: scoped-to-the-paid-invoice-own-school
        match = (
            EventRegistration.objects.filter(
                event__school_id=school_id,
                status=EventRegistration.Status.RESERVED,
                metadata__invoice_id=invoice.pk,
            )
            .order_by("pk")
            .first()
        )
    except Exception:  # noqa: BLE001 -- a ticket lookup never breaks a payment
        logger.debug(
            "Could not resolve an event registration for invoice %s",
            getattr(invoice, "pk", None),
            exc_info=True,
        )
        return None
    return None if match is None else match.pk


def _maybe_confirm_event_registration(
    *,
    payload: dict,
    invoice,
    amount,
    method: str,
    reference: str,
) -> None:
    """Best-effort: settle event ticket holds linked via metadata (Metric #13).

    Looks for ``event_registration_id`` on the webhook payload, nested metadata,
    or ``invoice.metadata``. Failures are logged and never roll back a posted
    Payment — ticket state is secondary to ledger integrity.
    """
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    invoice_meta = getattr(invoice, "metadata", None)
    invoice_meta = invoice_meta if isinstance(invoice_meta, dict) else {}
    raw = (
        payload.get("event_registration_id")
        or payload.get("eventRegistrationId")
        or metadata.get("event_registration_id")
        or metadata.get("eventRegistrationId")
        or data_block.get("event_registration_id")
        or invoice_meta.get("event_registration_id")
    )
    if raw is None or str(raw).strip() == "":
        # No id on the callback -- which is the NORMAL case, not an edge one.
        # Nothing in the product puts event_registration_id into a PSP payload,
        # and the invoice_meta fallback above is permanently {} because Invoice
        # has no metadata field at all. create_ticket_invoice_for_registration
        # does store the link durably, just the other way round --
        # registration.metadata['invoice_id'] -- and writes the reverse only into
        # invoice.notes as free text, which nothing reads. Follow the link that
        # exists, scoped to this invoice's own school so it can no more cross a
        # tenant than the forward path can.
        raw = _registration_id_for_invoice(invoice)
    if raw is None or str(raw).strip() == "":
        return
    try:
        registration_id = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring non-integer event_registration_id=%r on webhook %s",
            raw,
            reference,
        )
        return
    try:
        from apps.school_events.models import EventRegistration
        from apps.school_events.services import (
            RegistrationStateError,
            confirm_registration_from_psp,
        )

        confirm_registration_from_psp(
            registration_id=registration_id,
            # The id came off the webhook body, so it is attacker-influenced.
            # Bind it to the school whose invoice this payment settled.
            school=getattr(invoice, "school", None),
            amount=amount,
            method=method or "psp",
            reference=reference,
        )
    except EventRegistration.DoesNotExist:
        # Not an error path worth a stack trace: either the id is stale, or the
        # webhook named a registration belonging to a different school. Both are
        # refusals, and the second is worth seeing in the log as one.
        logger.warning(
            "Webhook %s named event registration %s, which does not belong to "
            "invoice school %s -- refusing to confirm",
            reference,
            registration_id,
            getattr(getattr(invoice, "school", None), "pk", None),
        )
    except RegistrationStateError as exc:
        logger.info(
            "Event registration %s not confirmable after webhook %s: %s",
            registration_id,
            reference,
            exc,
        )
    except Exception:
        logger.exception(
            "Failed confirming event registration %s after webhook %s",
            registration_id,
            reference,
        )


@csrf_exempt
@require_http_methods(["POST"])
def payment_provider_webhook(request: HttpRequest, provider_slug: str):
    """
    Secure webhook endpoint for payment provider callbacks.
    Security: method validation, provider validation, IP whitelist, rate limit,
    HMAC signature, idempotency, payment validation, transaction integrity.
    Audit: All attempts logged to WebhookLog.
    """
    integration = get_payment_integration_by_slug(provider_slug)
    if not integration:
        logger.warning("Webhook request for unknown provider: %s", provider_slug)
        return HttpResponseForbidden("Unknown provider.")

    def _provider_code() -> str:
        configured = (
            normalize_provider_slug((integration.config or {}).get("provider_slug"))
            if integration
            else ""
        )
        return (
            configured
            or normalize_provider_slug(provider_slug)
            or (provider_slug or "").strip().lower()
        )

    provider_code = _provider_code()
    validator = WebhookSecurityValidator(integration.config or {})
    client_ip = validator.get_client_ip(request)
    request_body = request.body
    _idem_header = (
        request.headers.get("Idempotency-Key")
        or request.META.get("HTTP_IDEMPOTENCY_KEY")
        or ""
    ).strip()[:160]

    def _request_content_type() -> str:
        return (
            (request.content_type or request.META.get("CONTENT_TYPE") or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )

    def _content_type_is_json() -> bool:
        ct = _request_content_type()
        return ct == "application/json" or ct.endswith("+json")

    def _request_body_excerpt(raw_body: bytes | None = None) -> str:
        body = request_body if raw_body is None else raw_body
        return (body or b"").decode("utf-8", errors="replace")[:500]

    def _first_present(payload: dict, keys: list[str]):
        for key in keys:
            if key in payload and payload.get(key) not in (None, ""):
                return payload.get(key)
        return None

    def _as_dict(value):
        return value if isinstance(value, dict) else {}

    def _extract_reference(payload: dict) -> str:
        metadata = _as_dict(payload.get("metadata"))
        data_block = _as_dict(payload.get("data"))
        txn_block = _as_dict(payload.get("transaction"))
        value = (
            _first_present(
                payload,
                [
                    "reference",
                    "payment_reference",
                    "transaction_id",
                    "transactionId",
                    "external_reference",
                    "txid",
                    "id",
                ],
            )
            or _first_present(
                data_block,
                [
                    "reference",
                    "payment_reference",
                    "transaction_id",
                    "transactionId",
                    "external_reference",
                    "txid",
                    "id",
                ],
            )
            or _first_present(
                txn_block,
                [
                    "reference",
                    "payment_reference",
                    "transaction_id",
                    "transactionId",
                    "external_reference",
                    "txid",
                    "id",
                ],
            )
            or _first_present(
                metadata,
                [
                    "reference",
                    "payment_reference",
                    "transaction_id",
                    "transactionId",
                    "external_reference",
                    "txid",
                ],
            )
        )
        return str(value or "").strip()

    def _extract_invoice_id(payload: dict) -> int | None:
        metadata = _as_dict(payload.get("metadata"))
        data_block = _as_dict(payload.get("data"))
        candidates = [
            _first_present(
                payload, ["invoice_id", "invoice", "invoiceId", "invoiceID"]
            ),
            _first_present(
                data_block, ["invoice_id", "invoice", "invoiceId", "invoiceID"]
            ),
            _first_present(
                metadata, ["invoice_id", "invoice", "invoiceId", "invoiceID"]
            ),
        ]
        for value in candidates:
            if value is None:
                continue
            try:
                text = str(value).strip()
                if not text:
                    continue
                return int(text)
            except (TypeError, ValueError):
                continue
        return None

    def _extract_amount(payload: dict):
        metadata = _as_dict(payload.get("metadata"))
        data_block = _as_dict(payload.get("data"))
        txn_block = _as_dict(payload.get("transaction"))
        return (
            _first_present(payload, ["amount", "paid_amount", "transaction_amount"])
            or _first_present(
                data_block, ["amount", "paid_amount", "transaction_amount"]
            )
            or _first_present(
                txn_block, ["amount", "paid_amount", "transaction_amount"]
            )
            or _first_present(metadata, ["amount", "paid_amount", "transaction_amount"])
        )

    def _extract_method(payload: dict, prov_code: str) -> str:
        raw_method = (
            _first_present(payload, ["method", "payment_method", "channel"]) or ""
        )
        normalized_method = str(raw_method).strip().upper().replace("-", "_")
        method_aliases = {
            "MTN": PaymentMethodCode.MTN_MOMO,
            "MTN_MOMO": PaymentMethodCode.MTN_MOMO,
            "MOBILE_MONEY_MTN": PaymentMethodCode.MTN_MOMO,
            "ORANGE": PaymentMethodCode.ORANGE_MOMO,
            "ORANGE_MONEY": PaymentMethodCode.ORANGE_MOMO,
            "ORANGE_MOMO": PaymentMethodCode.ORANGE_MOMO,
            "MOBILE_MONEY_ORANGE": PaymentMethodCode.ORANGE_MOMO,
        }
        if normalized_method in method_aliases:
            return method_aliases[normalized_method]
        return (
            PROVIDER_SLUG_TO_METHOD.get(prov_code)
            or PROVIDER_SLUG_TO_METHOD.get(provider_slug)
            or PaymentMethodCode.MTN_MOMO
        )

    def _create_webhook_log(
        *,
        reference_id: str,
        status: str,
        signature_valid: bool = False,
        response_status: int | None = None,
        invoice: Invoice | None = None,
        payment: Payment | None = None,
        error_message: str = "",
    ) -> WebhookLog:
        # Audit / reject / duplicate rows never claim the idempotency bucket —
        # only the authoritative processing row minted by claim_webhook_processing
        # owns it (bucket stays "" here, exempt from the unique constraint). If an
        # audit row persisted the bucket it would collide with
        # finance_webhooklog_uniq_provider_bucket on any duplicate or rejected
        # redelivery (IntegrityError -> 500 retry storm), and a rejected first
        # delivery owning the bucket would make the real payment's later claim
        # resolve as a false "duplicate" and never post.
        payload_dict: dict = {
            "provider": provider_code,
            "reference_id": reference_id,
            "client_ip": client_ip,
            "signature_valid": signature_valid,
            "status": status,
            "request_body": _request_body_excerpt(),
        }
        if response_status is not None:
            payload_dict["response_status"] = response_status
        if invoice is not None:
            payload_dict["invoice"] = invoice
        if payment is not None:
            payload_dict["payment"] = payment
        if error_message:
            payload_dict["error_message"] = error_message
        return WebhookLog.objects.create(**payload_dict)

    if request_body and not _content_type_is_json():
        _create_webhook_log(
            reference_id="unknown",
            status=WebhookLog.Status.INVALID,
            response_status=415,
            error_message=f"Unsupported content type: {_request_content_type() or 'unknown'}",
        )
        return HttpResponse("Content-Type must be application/json.", status=415)

    try:
        data = json.loads((request_body or b"{}").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Invalid webhook payload from %s: %s", provider_slug, e)
        _create_webhook_log(
            reference_id="unknown",
            status=WebhookLog.Status.INVALID,
            response_status=400,
            error_message=f"Invalid JSON: {str(e)}",
        )
        return HttpResponseBadRequest("Invalid JSON payload.")
    if not isinstance(data, dict):
        _create_webhook_log(
            reference_id="unknown",
            status=WebhookLog.Status.INVALID,
            response_status=400,
            error_message="Webhook payload must be a JSON object",
        )
        return HttpResponseBadRequest("Webhook payload must be a JSON object.")

    from apps.finance.webhooks.normalizer import (
        is_explicit_non_success,
        normalize_provider_payload,
    )

    metadata_block = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    canonical_event = normalize_provider_payload(
        provider_code,
        data,
        metadata=metadata_block,
    )
    reference_id = _extract_reference(data) or "unknown"
    if canonical_event is not None and canonical_event.event_id:
        reference_id = canonical_event.event_id
    from apps.finance.webhook_ingress import resolve_webhook_dedup_bucket

    header_map = {
        str(k): v for k, v in request.headers.items()
    } if hasattr(request, "headers") else {}
    dedup_reference = resolve_webhook_dedup_bucket(
        provider_code,
        data,
        headers=header_map,
        idempotency_header=_idem_header,
        reference_fallback=reference_id,
    )

    if not validator.validate_ip_whitelist(client_ip):
        _create_webhook_log(
            reference_id=reference_id,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message=f"IP not whitelisted: {client_ip}",
        )
        logger.warning(
            "Rejected webhook from unauthorized IP %s for %s", client_ip, provider_slug
        )
        return HttpResponseForbidden("IP not whitelisted.")

    if not validator.validate_rate_limit(client_ip):
        _create_webhook_log(
            reference_id=reference_id,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message=f"Rate limit exceeded for IP {client_ip}",
        )
        logger.warning("Rate limit exceeded for IP %s", client_ip)
        return HttpResponseForbidden("Rate limit exceeded.")

    # Signature verification. An Integration may opt into a provider-accurate
    # verifier (Stripe / Paystack / Flutterwave / M-Pesa Daraja / aggregator) via
    # config["signature_scheme"]; when the key is absent — every integration
    # shipped to date — we keep the exact historical generic HMAC path below, so
    # this is purely additive and changes no live behaviour until an operator
    # opts a specific integration in. An explicit-but-unknown scheme fails closed.
    from apps.finance.webhooks.signature_dispatch import (
        scheme_from_config,
        verify_provider_signature,
    )

    _sig_scheme = scheme_from_config(integration.config)
    if _sig_scheme:
        signature_valid, _sig_fail_reason = verify_provider_signature(
            _sig_scheme,
            headers=header_map,
            raw_body=request_body,
            secret=(integration.config or {}).get("webhook_secret", ""),
            config=integration.config or {},
        )
        if not signature_valid:
            logger.warning(
                "Provider-accurate signature check failed for %s (scheme=%s): %s",
                provider_slug,
                _sig_scheme,
                _sig_fail_reason,
            )
    else:
        signature_header = (
            integration.config.get("signature_header", "X-Signature")
            if integration.config
            else "X-Signature"
        )
        signature = request.headers.get(signature_header) or request.META.get(
            f"HTTP_{signature_header.upper().replace('-', '_')}"
        )
        signature_valid = validator.validate_signature(request_body, signature or "")
    if not signature_valid:
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=False,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message="Invalid HMAC signature",
        )
        logger.warning("Invalid signature from %s (%s)", provider_slug, client_ip)
        return HttpResponseForbidden("Invalid signature.")

    timestamp_header = (
        integration.config.get("timestamp_header", "X-Timestamp")
        if integration.config
        else "X-Timestamp"
    )
    request_timestamp = request.headers.get(timestamp_header) or request.META.get(
        f"HTTP_{timestamp_header.upper().replace('-', '_')}"
    )
    if not validator.validate_timestamp(request_timestamp):
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message="Invalid or stale webhook timestamp",
        )
        logger.warning("Invalid timestamp from %s (%s)", provider_slug, client_ip)
        return HttpResponseForbidden("Invalid timestamp.")

    # Dead-letter queue: stop hammering after repeated failures (idempotency-Key still dedupes success path)
    from django.conf import settings as dj_settings

    _dl_window_h = int(getattr(dj_settings, "WEBHOOK_DEAD_LETTER_WINDOW_HOURS", 24))
    _dl_thresh = int(getattr(dj_settings, "WEBHOOK_DEAD_LETTER_FAILURE_THRESHOLD", 5))
    _since = timezone.now() - timedelta(hours=_dl_window_h)
    _fail_ct = WebhookLog.objects.filter(
        provider=provider_code,
        reference_id=reference_id,
        status=WebhookLog.Status.FAILED,
        created_at__gte=_since,
    ).count()
    if _fail_ct >= _dl_thresh and reference_id != "unknown":
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.DEAD_LETTER,
            response_status=200,
            error_message=f"Exceeded {_dl_thresh} FAILED in {_dl_window_h}h; ack 200 to stop retries",
        )
        logger.warning(
            "Webhook dead-letter for %s ref=%s (failures=%s)",
            provider_slug,
            reference_id,
            _fail_ct,
        )
        return JsonResponse(
            {
                "status": "dead_letter",
                "reason": "max_processing_failures",
                "reference_id": reference_id,
            },
            status=200,
        )

    invoice_id = _extract_invoice_id(data)
    amount = _extract_amount(data)
    method = _extract_method(data, provider_code)

    # Prefer canonical normalizer fields when top-level extractors miss
    # provider-specific nests (e.g. M-Pesa Daraja STK CallbackMetadata).
    if canonical_event is not None:
        if not invoice_id and canonical_event.invoice_id:
            invoice_id = canonical_event.invoice_id
        if (
            (amount is None or str(amount).strip() in {"", "0", "0.0", "0.00"})
            and canonical_event.amount_decimal is not None
            and canonical_event.amount_decimal > 0
        ):
            amount = canonical_event.amount_decimal
        if not reference_id or reference_id == "unknown":
            if canonical_event.event_id:
                reference_id = canonical_event.event_id

    # SFDP: a validly-signed webhook that EXPLICITLY reports a non-success status
    # (failed / declined / cancelled / reversed / pending …) must never post a
    # Payment — record_provider_payment feeds the fractional ledger and grants
    # enrollment clearance, so posting a failed callback would clear a student who
    # never paid. Gate ONLY on an explicit status: an empty/undetermined status
    # (a provider that omits it) preserves prior behaviour, so no legitimate
    # payment is blocked. The success vocabulary is normalized in the normalizer.
    if is_explicit_non_success(canonical_event):
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=200,
            error_message=(
                f"Non-success PSP status '{canonical_event.status}' — no payment posted"
            ),
        )
        logger.info(
            "Ignoring non-success %s webhook ref=%s status=%s (no payment posted)",
            provider_slug,
            reference_id,
            canonical_event.status,
        )
        return JsonResponse(
            {
                "status": "ignored",
                "reason": "psp_status_not_success",
                "psp_status": canonical_event.status,
            },
            status=200,
        )

    is_valid, error_msg = PaymentValidator.validate_amount(amount)
    if not is_valid:
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=400,
            error_message=f"Invalid amount: {error_msg}",
        )
        logger.warning("Invalid payment amount from %s: %s", provider_slug, amount)
        return HttpResponseBadRequest(error_msg)

    if not invoice_id:
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=400,
            error_message="Missing invoice_id in payload",
        )
        return HttpResponseBadRequest("Missing invoice_id.")

    try:
        # tenant-isolation-allow: primary-key lookup on an id the PAYMENT PROVIDER
        # echoed back to us, in an unauthenticated webhook that has no tenant
        # context to be scoped by - the request is authorised by signature, not by
        # session. Reviewed 2026-09-02.
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=400,
            error_message=f"Invoice {invoice_id} not found",
        )
        logger.warning(
            "Invoice %s not found from webhook %s", invoice_id, provider_slug
        )
        return HttpResponseBadRequest(f"Invoice {invoice_id} not found.")

    # Net received, NOT a gross sum of every payment row. The gross sum counted
    # soft-deleted, failed, cancelled and refunded attempts at face value, so a
    # legitimate signed callback on an invoice with any reversed history was
    # rejected 400 "exceeds remaining balance 0" — and past the dead-letter
    # threshold the endpoint started acking 200 and dropping the money.
    # Idempotency outranks amount validation. A redelivery of an event that
    # already SETTLED this invoice has nothing left to allocate, so the
    # validate_against_invoice call below computes remaining == 0 and answers
    # HTTP 400 "exceeds remaining balance 0" -- a permanent 4xx that every PSP
    # reads as "keep retrying", forever, for an event we already processed
    # correctly. The dedup claim that WOULD have acked it 200 sits further
    # down and is never reached on that path. So probe the bucket read-only
    # here, before any amount arithmetic: when a terminal log already owns it
    # this delivery is a replay, and the only correct answer is the duplicate
    # ack. A first delivery owns no terminal row and is unaffected; the
    # in-flight (PROCESSING) race is still resolved by claim_webhook_processing.
    if dedup_reference:
        from apps.finance.webhook_ingress import duplicate_webhook_response
        from apps.finance.webhooks.idempotency import find_processed_duplicate

        if find_processed_duplicate(provider_code, dedup_reference) is not None:
            _create_webhook_log(
                reference_id=reference_id,
                signature_valid=True,
                status=WebhookLog.Status.DUPLICATE,
                response_status=200,
                invoice=invoice,
            )
            logger.info(
                "Duplicate webhook from %s: %s (already terminal; not re-validated)",
                provider_slug,
                dedup_reference,
            )
            return duplicate_webhook_response()

    invoice_paid = invoice.total_amount - invoice.computed_balance
    is_valid, error_msg = PaymentValidator.validate_against_invoice(
        Decimal(str(amount)),
        invoice.total_amount,
        invoice_paid,
    )
    if not is_valid:
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=400,
            invoice=invoice,
            error_message=f"Amount validation failed: {error_msg}",
        )
        logger.warning(
            "Payment amount validation failed for invoice %s: %s",
            invoice_id,
            error_msg,
        )
        return HttpResponseBadRequest(error_msg)

    try:
        with transaction.atomic():
            from apps.finance.webhook_ingress import duplicate_webhook_response
            from apps.finance.webhooks.claim import claim_webhook_processing

            claim_result, webhook_log = claim_webhook_processing(
                provider=provider_code,
                bucket=dedup_reference,
                reference_id=reference_id,
                client_ip=client_ip,
                request_body_excerpt=_request_body_excerpt(),
            )
            if claim_result == "duplicate":
                _create_webhook_log(
                    reference_id=reference_id,
                    signature_valid=True,
                    status=WebhookLog.Status.DUPLICATE,
                    response_status=200,
                )
                logger.info(
                    "Duplicate webhook from %s: %s", provider_slug, dedup_reference
                )
                return duplicate_webhook_response()

            payment = record_provider_payment(
                invoice=invoice,
                amount=amount,
                method=method or PaymentMethodCode.MTN_MOMO,
                reference=_extract_reference(data),
                external_reference=reference_id,
            )
            if not payment:
                if webhook_log is not None:
                    webhook_log.status = WebhookLog.Status.FAILED
                    webhook_log.error_message = "Failed to create payment record"
                    webhook_log.response_status = 500
                    webhook_log.save(
                        update_fields=["status", "error_message", "response_status"]
                    )
                logger.error("Failed to record payment for webhook %s", reference_id)
                return JsonResponse(
                    {"status": "error", "reason": "payment_creation_failed"}
                )
            if webhook_log is not None:
                webhook_log.invoice = invoice
                webhook_log.payment = payment
                webhook_log.status = WebhookLog.Status.PROCESSED
                webhook_log.response_status = 200
                webhook_log.save(
                    update_fields=["invoice", "payment", "status", "response_status"]
                )
            else:
                _create_webhook_log(
                    reference_id=reference_id,
                    signature_valid=True,
                    status=WebhookLog.Status.PROCESSED,
                    invoice=invoice,
                    payment=payment,
                    response_status=200,
                )
            _maybe_confirm_event_registration(
                payload=data,
                invoice=invoice,
                amount=amount,
                method=method or PaymentMethodCode.OTHER,
                reference=reference_id,
            )
            logger.info(
                "Successfully processed webhook from %s: Invoice %s, Payment %s, Amount %s",
                provider_slug,
                invoice_id,
                payment.id,
                amount,
            )
            return JsonResponse(
                {
                    "status": "ok",
                    "payment_id": payment.id,
                    "reference": reference_id,
                }
            )
    except FINANCE_SOFT_FAILURES as e:
        logger.exception("Transaction error processing webhook %s: %s", reference_id, e)
        # (reference_id, provider) is NOT unique — audit/reject rows are written
        # with idempotency_bucket="" — so .get() here could raise
        # MultipleObjectsReturned, an uncaught 500 that also drops the status
        # write. Take the most recent matching row instead.
        webhook_log = (
            WebhookLog.objects.filter(
                reference_id=reference_id, provider=provider_code
            )
            .order_by("-id")
            .first()
        )
        if webhook_log is not None:
            webhook_log.status = WebhookLog.Status.FAILED
            webhook_log.error_message = f"Transaction error: {str(e)[:200]}"
            webhook_log.response_status = 500
            webhook_log.save(
                update_fields=["status", "error_message", "response_status"]
            )
        else:
            _create_webhook_log(
                reference_id=reference_id,
                signature_valid=True,
                status=WebhookLog.Status.FAILED,
                response_status=500,
                error_message=f"Transaction error: {str(e)[:200]}",
            )
        return JsonResponse(
            {"status": "error", "reason": "processing_failed"}, status=500
        )
