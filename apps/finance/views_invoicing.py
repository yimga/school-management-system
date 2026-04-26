"""
Finance invoicing views (§6.15 app-by-app split — subdomain: invoicing).

Invoice list/detail, receipt, fee generation, guardian notifications,
receipt upload, and resend reminder. Single place for invoice-related UI flows.
"""

from __future__ import annotations

import csv
import io
import logging
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.template.loader import render_to_string

from apps.academics.models import AcademicYear
from apps.platform_runtime.site_settings_read_access import get_effective_site_settings

from .models import (
    FeePlan,
    Invoice,
    InvoicePayerShare,
    Payment,
    PaymentMethodCode,
    PaymentProofUpload,
)
from .notifications import notify_guardians_new_invoices_bulk
from .services import create_fee_invoices, generate_payment_link
from .fraud_detection import ReceiptFraudDetector
from .views_common import (
    FINANCE_SOFT_FAILURES,
    _active_profile,
    _finance_access_state,
    _notify_finance_staff_suspicious_receipt,
)

logger = logging.getLogger(__name__)

SESSION_KEY_LAST_GENERATED_INVOICE_IDS = "finance_last_generated_invoice_ids"


@login_required
def invoice_list(request: HttpRequest):
    """
    Invoice list view with role-based filtering.
    Staff see all invoices; parents see only their children's invoices.
    """
    from apps.accounts.models import User
    from apps.accounts.permissions import _guardian_finance_qs

    access_state = _finance_access_state(request.user, request)
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    status = request.GET.get("status")
    year_id = request.GET.get("year")
    search = (request.GET.get("q") or "").strip()
    qs = (
        Invoice.objects.filter(profile=profile)
        .select_related("student", "academic_year", "profile")
        .prefetch_related(
            "payments",
            "student__guardian_links",
            Prefetch(
                "payer_shares",
                queryset=(
                    InvoicePayerShare.objects.filter(is_active=True).select_related(
                        "guardian", "guardian__guardian_user"
                    )
                ),
                to_attr="active_payer_shares",
            ),
        )
    )

    if request.user.role == User.Role.PARENT:
        parent_students = _guardian_finance_qs(request.user).values_list(
            "student_id", flat=True
        )
        qs = qs.filter(student_id__in=parent_students)
        if access_state["require_opt_in"] and not access_state["finance_count"]:
            qs = qs.none()
    elif not (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.role == User.Role.ADMIN
    ):
        return HttpResponseForbidden("You don't have permission to view invoices.")

    if status:
        qs = qs.filter(status=status)
    if year_id:
        qs = qs.filter(academic_year_id=year_id)
    if search:
        qs = qs.filter(
            models.Q(reference__icontains=search)
            | models.Q(student__first_name__icontains=search)
            | models.Q(student__last_name__icontains=search)
            | models.Q(student__admission_number__icontains=search)
        )

    _invoice_order_map = {
        "issued_date": "issued_date",
        "-issued_date": "-issued_date",
        "due_date": "due_date",
        "-due_date": "-due_date",
        "total_amount": "total_amount",
        "-total_amount": "-total_amount",
    }
    order_param = (request.GET.get("order") or "").strip()
    order_by = _invoice_order_map.get(order_param, "-issued_date")
    ordered_qs = qs.order_by(order_by)

    if request.GET.get("export") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "Reference",
                "Type",
                "Status",
                "Due",
                "Student",
                "Total",
                "Balance",
                "Issued",
            ]
        )
        for inv in ordered_qs[:5000]:
            w.writerow(
                [
                    inv.reference or str(inv.id),
                    inv.get_invoice_type_display(),
                    inv.get_status_display(),
                    inv.due_date.isoformat() if inv.due_date else "",
                    str(inv.student) if inv.student_id else "",
                    str(inv.total_amount),
                    str(inv.balance_amount),
                    inv.issued_date.isoformat() if inv.issued_date else "",
                ]
            )
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="invoices_export.csv"'
        return resp

    if request.GET.get("export") == "pdf":
        try:
            from weasyprint import HTML
        except ImportError:
            return HttpResponse("PDF export requires WeasyPrint.", status=503)

        def _d(d):
            return d.strftime("%Y-%m-%d") if d else ""

        rows_html = "".join(
            f"<tr><td>{inv.reference or inv.id}</td><td>{inv.get_invoice_type_display()}</td>"
            f"<td>{inv.get_status_display()}</td><td>{_d(inv.due_date)}</td>"
            f"<td>{inv.student or ''}</td><td>{inv.total_amount}</td><td>{inv.balance_amount}</td>"
            f"<td>{_d(inv.issued_date)}</td></tr>"
            for inv in ordered_qs[:500]
        )
        site = get_effective_site_settings(request=request)
        title = getattr(site, "site_name", None) or "Invoices"
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Invoices</title>
<style>body{{font-family:system-ui,sans-serif;font-size:10pt;margin:12mm;}}
table{{width:100%;border-collapse:collapse;}} th,td{{border:1px solid #ddd;padding:6px;text-align:left;}}
th{{background:#f5f5f5;}} .header{{margin-bottom:12px;}}</style></head>
<body><div class="header"><h1>{title}</h1><p>Invoices export</p></div>
<table><thead><tr><th>Reference</th><th>Type</th><th>Status</th><th>Due</th><th>Student</th><th>Total</th><th>Balance</th><th>Issued</th></tr></thead>
<tbody>{rows_html}</tbody></table></body></html>"""
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = 'attachment; filename="invoices_export.pdf"'
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

    current_user_id = getattr(request.user, "id", None)
    for inv in page_obj.object_list:
        shares = getattr(inv, "active_payer_shares", []) or []
        inv.split_payer_count = len(shares)
        inv.split_outstanding_total = sum(
            (share.outstanding_amount for share in shares),
            Decimal("0.00"),
        )
        inv.my_split_outstanding = None
        inv.my_split_status = ""
        if current_user_id and shares:
            mine = next(
                (
                    share
                    for share in shares
                    if share.guardian.guardian_user_id == current_user_id
                ),
                None,
            )
            if mine:
                inv.my_split_outstanding = mine.outstanding_amount
                inv.my_split_status = mine.get_status_display()

    return render(
        request,
        "finance/invoices.html",
        {
            "invoices": page_obj,
            "statuses": Invoice.Status.choices,
            "selected_status": status or "",
            "years": AcademicYear.objects.order_by("-start_date"),
            "selected_year": year_id or "",
            "search": search,
            "page_obj": page_obj,
            "paginator": paginator,
            "pagination_extra_query": pagination_extra_query,
            "finance_access_required": access_state["require_opt_in"],
            "finance_access_granted": access_state["finance_count"] > 0,
            "finance_guardian_count": access_state["finance_count"],
            "guardian_link_count": access_state["guardian_count"],
            "finance_access_summary": (
                f"{access_state['finance_count']} of {access_state['guardian_count']} linked student(s) currently have finance access."
                if access_state["guardian_count"]
                else None
            ),
            "can_request_finance_access": (
                access_state["allow_requests"]
                and access_state["require_opt_in"]
                and access_state["guardian_count"] > access_state["finance_count"]
            ),
            "finance_request_url": reverse("finance:finance_request_access"),
            "page_title": "Invoices",
            "page_subtitle": "Accounts receivable and payable.",
            "action_url": reverse("finance:dashboard"),
            "order_options": [
                ("-issued_date", "Date (newest first)"),
                ("issued_date", "Date (oldest first)"),
                ("-due_date", "Due date (latest first)"),
                ("due_date", "Due date (earliest first)"),
                ("-total_amount", "Amount (high to low)"),
                ("total_amount", "Amount (low to high)"),
            ],
            "selected_order": order_param or "-issued_date",
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def generate_fees(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    plans = FeePlan.objects.filter(is_active=True).select_related(
        "academic_year", "classroom", "specialty"
    )

    if request.method == "POST":
        plan_id = request.POST.get("plan_id")
        if not plan_id:
            messages.error(request, "Please select a fee plan.")
            return redirect("finance:generate_fees")

        plan = get_object_or_404(FeePlan, id=plan_id)
        issued_date = timezone.now().date()
        invoices = create_fee_invoices(
            plan=plan, profile=profile, issued_date=issued_date
        )
        request.session[SESSION_KEY_LAST_GENERATED_INVOICE_IDS] = [
            inv.id for inv in invoices
        ]
        messages.success(
            request,
            f"Generated {len(invoices)} invoices. You can notify guardians below.",
        )
        return redirect("finance:generate_fees")

    invoice_ids = request.session.get(SESSION_KEY_LAST_GENERATED_INVOICE_IDS) or []
    return render(
        request,
        "finance/generate_fees.html",
        {
            "plans": plans,
            "last_generated_invoice_ids": invoice_ids,
            "last_generated_count": len(invoice_ids),
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
@require_POST
def notify_guardians_new_invoices(request: HttpRequest):
    """Send new-invoice notifications to guardians for the last bulk-generated invoices."""
    invoice_ids = (
        request.session.pop(SESSION_KEY_LAST_GENERATED_INVOICE_IDS, None) or []
    )
    if not invoice_ids:
        messages.info(request, "No recent invoices to notify. Generate invoices first.")
        return redirect("finance:generate_fees")
    total = notify_guardians_new_invoices_bulk(
        invoice_ids,
        created_by=request.user,
        send_email=getattr(
            get_effective_site_settings(request=request),
            "finance_notify_new_invoice_email",
            False,
        ),
    )
    messages.success(
        request, f"Notifications sent to {total} guardian(s) for the new invoices."
    )
    return redirect("finance:invoices")


@login_required
def invoice_detail(request: HttpRequest, invoice_id: int):
    """
    Invoice detail view with object-level permission check.
    Staff can view all invoices; parents can only view their children's invoices.
    """
    from apps.accounts.permissions import can_view_invoice
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian

    access_state = _finance_access_state(request.user, request)
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    invoice = get_object_or_404(
        Invoice.objects.select_related(
            "student", "academic_year", "profile", "counterparty"
        ).prefetch_related("payments", "lines"),
        id=invoice_id,
        profile=profile,
    )

    can_view = can_view_invoice(request.user, invoice_id)
    if not can_view:
        is_parent = getattr(request.user, "role", "") == User.Role.PARENT
        is_guardian = bool(
            invoice.student_id
            and StudentGuardian.objects.filter(
                guardian_user=request.user,
                student_id=invoice.student_id,
            ).exists()
        )
        if is_parent and is_guardian:
            summary = None
            if access_state["guardian_count"]:
                summary = (
                    f"{access_state['finance_count']} of {access_state['guardian_count']} "
                    "linked student(s) currently have finance access."
                )
            return render(
                request,
                "finance/invoice_detail.html",
                {
                    "access_denied": True,
                    "invoice_stub": {
                        "reference": invoice.reference or invoice.id,
                        "student": invoice.student,
                    },
                    "finance_access_required": access_state["require_opt_in"],
                    "finance_access_granted": access_state["finance_count"] > 0,
                    "finance_access_summary": summary,
                    "can_request_finance_access": (
                        access_state["allow_requests"]
                        and access_state["require_opt_in"]
                    ),
                    "finance_request_url": reverse(
                        "finance:invoice_request_access", args=[invoice.id]
                    ),
                },
                status=403,
            )
        return HttpResponseForbidden("You don't have permission to view this invoice.")

    if request.method == "POST" and request.FILES.get("attachment"):
        from apps.accounts.validators import FileTypeValidator, FileSizeValidator

        up = request.FILES["attachment"]
        try:
            FileTypeValidator(
                allowed_extensions=[
                    ".pdf",
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                    ".odt",
                    ".ods",
                ],
                allowed_types=[
                    "application/pdf",
                    "application/msword",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.ms-excel",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/vnd.oasis.opendocument.text",
                    "application/vnd.oasis.opendocument.spreadsheet",
                ],
                message="Only document files (PDF, Word, Excel, or LibreOffice ODT/ODS) are allowed.",
            )(up)
            FileSizeValidator(max_size_mb=5)(up)
        except ValidationError as e:
            messages.error(
                request, e.messages[0] if getattr(e, "messages", None) else str(e)
            )
            return redirect("finance:invoice_detail", invoice_id=invoice.id)
        invoice.attachment = up
        invoice.save(update_fields=["attachment"])
        messages.success(request, "Attachment uploaded.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    payment_link = generate_payment_link(invoice)
    reminder = getattr(invoice, "reminder", None)
    _reminder_logs = []
    if reminder:
        _reminder_logs = reminder.logs.order_by("-sent_at")[:10]

    finance_summary = None
    if access_state["guardian_count"]:
        finance_summary = (
            f"{access_state['finance_count']} of {access_state['guardian_count']} linked student(s) "
            "currently have finance access."
        )

    payer_shares = []
    guardian_share = None
    if invoice.student_id:
        payer_shares = list(
            invoice.payer_shares.filter(is_active=True).select_related(
                "guardian", "guardian__guardian_user"
            )
        )
        if payer_shares:
            current_guardian_share = next(
                (
                    share
                    for share in payer_shares
                    if share.guardian.guardian_user_id
                    == getattr(request.user, "id", None)
                ),
                None,
            )
            if current_guardian_share:
                guardian_share = {
                    "allocated": current_guardian_share.allocated_amount,
                    "paid": current_guardian_share.paid_amount,
                    "late_fee": current_guardian_share.late_fee_amount,
                    "outstanding": current_guardian_share.outstanding_amount,
                    "status": current_guardian_share.get_status_display(),
                    "due_date": current_guardian_share.due_date,
                }

    payment_proof_uploads = (
        PaymentProofUpload.objects.filter(invoice=invoice)
        .select_related("uploaded_by", "verified_by", "payment")
        .order_by("-created_at")
    )

    return render(
        request,
        "finance/invoice_detail.html",
        {
            "invoice": invoice,
            "payment_link": payment_link,
            "reminder": reminder,
            "payment_proof_uploads": payment_proof_uploads,
            "finance_access_required": access_state["require_opt_in"],
            "finance_access_granted": access_state["finance_count"] > 0,
            "finance_access_summary": finance_summary,
            "can_request_finance_access": (
                access_state["allow_requests"]
                and access_state["require_opt_in"]
                and access_state["guardian_count"] > access_state["finance_count"]
            ),
            "finance_request_url": reverse(
                "finance:invoice_request_access", args=[invoice.id]
            ),
            "finance_guardian_count": access_state["finance_count"],
            "guardian_link_count": access_state["guardian_count"],
            "guardian_share": guardian_share,
            "payer_share_count": len(payer_shares),
        },
    )


@login_required
@require_POST
def upload_payment_receipt(request: HttpRequest, invoice_id: int):
    """
    Allow parents/guardians to upload payment receipts for cash/bank payments.
    Receipts are automatically verified and payments applied if verification passes.
    """
    from decimal import InvalidOperation

    from apps.accounts.permissions import can_view_invoice
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian

    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    invoice = get_object_or_404(
        Invoice.objects.select_related("student"),
        id=invoice_id,
        profile=profile,
    )

    can_view = can_view_invoice(request.user, invoice_id)
    if not can_view:
        is_parent = getattr(request.user, "role", "") == User.Role.PARENT
        is_guardian = bool(
            invoice.student_id
            and StudentGuardian.objects.filter(
                guardian_user=request.user,
                student_id=invoice.student_id,
            ).exists()
        )
        if not (is_parent and is_guardian):
            return HttpResponseForbidden(
                "You don't have permission to upload receipts for this invoice."
            )

    if invoice.status == Invoice.Status.PAID:
        messages.error(request, "This invoice is already fully paid.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    site_settings = get_effective_site_settings(request=request)
    finance_runtime = (
        site_settings.get_finance_runtime_config()
        if callable(getattr(site_settings, "get_finance_runtime_config", None))
        else {}
    )
    if not finance_runtime.get(
        "receipt_upload_enabled",
        getattr(site_settings, "finance_receipt_upload_enabled", True),
    ):
        messages.error(request, "Receipt upload is currently disabled.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    receipt_file = request.FILES.get("receipt_file")
    if not receipt_file:
        messages.error(request, "Please select a receipt file to upload.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    max_mb = finance_runtime.get(
        "receipt_max_size_mb",
        getattr(site_settings, "finance_receipt_max_size_mb", 5),
    )
    max_bytes = max_mb * 1024 * 1024
    if receipt_file.size > max_bytes:
        messages.error(
            request,
            f"File is too large ({receipt_file.size / (1024 * 1024):.1f} MB). "
            f"Maximum allowed is {max_mb} MB. Please compress or use a smaller image.",
        )
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    allowed_ext = (
        (
            finance_runtime.get(
                "receipt_allowed_extensions",
                getattr(
                    site_settings,
                    "finance_receipt_allowed_extensions",
                    "pdf,jpg,jpeg,png",
                ),
            )
            or "pdf,jpg,jpeg,png"
        )
        .strip()
        .lower()
    )
    allowed_list = [e.strip().lstrip(".") for e in allowed_ext.split(",") if e.strip()]
    ext = (
        (receipt_file.name or "").split(".")[-1].lower()
        if "." in (receipt_file.name or "")
        else ""
    )
    if allowed_list and ext not in allowed_list:
        messages.error(
            request,
            f"File type '.{ext}' is not allowed. Use: {', '.join('.' + e for e in allowed_list)}. "
            "Please upload a PDF or image (e.g. photo of receipt).",
        )
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    payment_method = request.POST.get("payment_method", "")
    if payment_method not in [code[0] for code in PaymentMethodCode.choices]:
        messages.error(request, "Invalid payment method.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    transaction_reference = request.POST.get("transaction_reference", "").strip()
    idempotency_key = (request.POST.get("idempotency_key", "") or "").strip()[:64]
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else request.META.get("REMOTE_ADDR", "")
    ) or None
    user_agent = (request.META.get("HTTP_USER_AGENT", "") or "")[:500]
    uploaded_amount_str = request.POST.get("uploaded_amount", "").strip()
    uploaded_amount = None
    if uploaded_amount_str:
        try:
            uploaded_amount = Decimal(uploaded_amount_str)
        except (ValueError, InvalidOperation):
            messages.error(request, "Invalid amount format.")
            return redirect("finance:invoice_detail", invoice_id=invoice.id)

    notes = request.POST.get("notes", "").strip()

    fraud_detector = ReceiptFraudDetector()
    receipt_date = None
    fraud_result = fraud_detector.detect_fraud(
        receipt_file=receipt_file,
        receipt_date=receipt_date,
        transaction_reference=transaction_reference,
        uploaded_by_id=request.user.id,
        invoice_id=invoice.id,
        uploaded_amount=uploaded_amount,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    file_hash = fraud_result.get("file_hash", "")

    if file_hash:
        window_mins = finance_runtime.get(
            "receipt_idempotency_window_minutes",
            getattr(site_settings, "finance_receipt_idempotency_window_minutes", 10),
        )
        cutoff = timezone.now() - timedelta(minutes=window_mins)
        if PaymentProofUpload.objects.filter(
            invoice=invoice,
            uploaded_by=request.user,
            file_hash=file_hash,
            created_at__gte=cutoff,
        ).exists():
            messages.info(
                request,
                "This receipt was already received (same file). If payment was deducted but you saw an error, do not pay again; contact finance with your transaction reference.",
            )
            return redirect("finance:invoice_detail", invoice_id=invoice.id)

    proof_upload = PaymentProofUpload.objects.create(
        invoice=invoice,
        uploaded_by=request.user,
        receipt_file=receipt_file,
        payment_method=payment_method,
        transaction_reference=transaction_reference,
        uploaded_amount=uploaded_amount,
        verification_notes=notes,
        idempotency_key=idempotency_key or "",
        status=PaymentProofUpload.Status.PENDING,
        fraud_risk_score=fraud_result["fraud_risk_score"],
        fraud_flags=fraud_result["fraud_flags"],
        file_hash=fraud_result["file_hash"],
        is_suspicious=fraud_result["recommendation"] in ["review", "reject"],
        flagged_at=(
            timezone.now()
            if fraud_result["recommendation"] in ["review", "reject"]
            else None
        ),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if proof_upload.is_suspicious:
        _notify_finance_staff_suspicious_receipt(proof_upload, fraud_result)

    if finance_runtime.get(
        "receipt_auto_verify_enabled",
        getattr(site_settings, "finance_receipt_auto_verify_enabled", True),
    ):
        from apps.finance.tasks import process_payment_receipt_upload_task

        school_id = str(
            getattr(invoice, "school_id", None)
            or getattr(getattr(invoice, "student", None), "school_id", None)
            or ""
        )
        process_payment_receipt_upload_task.delay(
            proof_upload.id, school_id=school_id if school_id else None
        )
        messages.success(
            request,
            "Receipt uploaded successfully. It is being verified automatically. "
            "You will be notified once verification is complete.",
        )
    else:
        messages.success(
            request,
            "Receipt uploaded successfully. It will be reviewed by finance staff.",
        )

    return redirect("finance:invoice_detail", invoice_id=invoice.id)


@login_required
@require_POST
def resend_reminder(request: HttpRequest, invoice_id: int) -> HttpResponse:
    """Resend payment reminder immediately for an invoice."""
    from apps.accounts.permissions import can_view_invoice

    from .tasks import run_payment_reminders

    invoice = get_object_or_404(Invoice, id=invoice_id)

    if not request.user.is_staff:
        can_view = can_view_invoice(request.user, invoice_id)
        if not can_view:
            return HttpResponseForbidden(
                "You don't have permission to resend reminders for this invoice."
            )

    reminder = getattr(invoice, "reminder", None)
    if not reminder:
        messages.error(request, "No reminder configured for this invoice.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    if not reminder.is_active:
        messages.warning(request, "Reminder is inactive. Activate it first to resend.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    reminder.next_send_at = timezone.now() - timedelta(minutes=1)
    reminder.save(update_fields=["next_send_at"])

    try:
        result = run_payment_reminders()
        sent_count = result.get("sent", 0)
        if sent_count > 0:
            messages.success(
                request,
                f"Reminder sent successfully ({sent_count} channel(s): {', '.join(result.get('channels', {}).keys())}).",
            )
        else:
            messages.info(
                request,
                "Reminder queued but no sends occurred (may have been sent recently or no guardians configured).",
            )
    except FINANCE_SOFT_FAILURES as e:
        logger.error("Error resending reminder: %s", str(e))
        messages.error(request, f"Error resending reminder: {str(e)}")

    return redirect("finance:invoice_detail", invoice_id=invoice.id)


@staff_member_required(login_url=settings.LOGIN_URL)
def invoice_receipt(
    request: HttpRequest, invoice_id: int, payment_id: int | None = None
):
    profile = _active_profile(request)
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

    school_obj = getattr(invoice, "school", None) or getattr(request, "school", None)
    context = {
        "invoice": invoice,
        "payment": payment,
        "school": getattr(school_obj, "name", None) or profile.name,
        "school_obj": school_obj,
        "primary_color": getattr(school_obj, "primary_color", None) or "#0d6efd",
        "accent_color": getattr(school_obj, "accent_color", None) or "#198754",
        "logo_url": getattr(school_obj, "logo_url", None) or "",
    }
    # Pass request so i18n / LANGUAGE_CODE and other context processors apply (N3 print receipt).
    html = render_to_string("finance/receipt.html", context, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt-{payment.id}.pdf"'
    return response
