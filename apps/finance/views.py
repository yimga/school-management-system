from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, models, transaction
from django.db.models import Count, Q, Sum, Prefetch
from django.db.models.functions import Coalesce
from typing import Optional
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.utils.safestring import mark_safe

from django.template.loader import render_to_string

from apps.academics.models import AcademicYear
from apps.payroll.models import Payslip
from apps.platform_runtime.helpers import get_effective_flags, get_effective_site_settings
from apps.accounts.utils import get_dashboard_context
from apps.evals.notifications import NotificationService

from .forms import CashOfficeClosureForm, ReportRequestForm, SplitAllocationForm, TellerScanForm
from .bank_statement_import import BankStatementImportService
from .notifications import notify_guardians_new_invoices_bulk
from .ohada_reports import build_dsf_report
from .models import (
    ComplianceProfile,
    FeePlan,
    Invoice,
    InvoicePayerShare,
    InvoiceLine,
    LedgerAccount,
    Notification,
    FinanceRequestAudit,
    CashOfficeClosure,
    Payment,
    PaymentProofUpload,
    PaymentMethodCode,
    ReportRequest,
    SuspensePayment,
    WebhookLog,
)
from .fraud_detection import ReceiptFraudDetector
from .receipt_verification import ReceiptVerificationService
from .ocr_runtime import get_ocr_runtime_status
from .services import (
    assign_invoice_payer_shares,
    split_amount_equally,
    apply_payment,
    create_payment_from_receipt,
    PROVIDER_SLUG_TO_METHOD,
    create_fee_invoices,
    finance_dashboard_data,
    generate_payment_link,
    get_payment_integration_by_slug,
    normalize_provider_slug,
    record_provider_payment,
)
from .security import (
    PaymentValidator,
    WebhookSecurityValidator,
    webhook_security_required,
)
from apps.communication.models import Message

logger = logging.getLogger(__name__)
FINANCE_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    IntegrityError,
    LookupError,
    RuntimeError,
    TypeError,
    ValidationError,
    ValueError,
)


def _active_profile(request: HttpRequest | None = None) -> ComplianceProfile | None:
    site = get_effective_site_settings(request=request)
    if getattr(site, "compliance_profile", None):
        return site.compliance_profile
    return ComplianceProfile.objects.filter(is_active=True).first()


def _backend_flags(request: HttpRequest | None = None) -> dict:
    """
    Convenience wrapper to merge default backend flags with saved settings.
    Safe for use in early request handling where DB might be missing values.
    """
    try:
        return get_effective_flags(request)
    except FINANCE_SOFT_FAILURES:
        return {}


def _finance_access_state(user, request: HttpRequest | None = None) -> dict:
    """
    Snapshot of finance access for a guardian user.
    Returns counts, whether opt-in is required, and whether requests are allowed.
    """
    from apps.accounts.permissions import _guardian_finance_qs
    from apps.people.models import StudentGuardian

    flags = _backend_flags(request)
    guardian_qs = StudentGuardian.objects.filter(guardian_user=user)
    finance_qs = _guardian_finance_qs(user) if getattr(user, "is_authenticated", False) else StudentGuardian.objects.none()
    return {
        "require_opt_in": bool(flags.get("require_guardian_finance_opt_in")),
        "allow_requests": bool(flags.get("allow_finance_access_requests", True)),
        "guardian_count": guardian_qs.count(),
        "finance_count": finance_qs.count(),
        "guardian_names": [str(link.student) for link in guardian_qs.select_related("student")],
    }


def _log_finance_request_audit(notification: Notification | None, user, action: str, details: str = "") -> None:
    if not notification:
        return
    FinanceRequestAudit.objects.create(
        notification=notification,
        user=user,
        action=action,
        details=details or "",
    )


def _create_finance_request_notification(
    recipient,
    *,
    title: str,
    message: str,
    severity: str,
    created_by,
    action: str,
    details: str = "",
) -> Notification:
    notif = Notification.objects.create(
        title=title,
        message=message,
        severity=severity,
        recipient=recipient,
        created_by=created_by,
    )
    _log_finance_request_audit(notif, created_by, action, details)
    return notif


@staff_member_required
def dashboard(request: HttpRequest):
    profile = _active_profile(request)
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
            {"label": "Overdue list", "url": reverse("finance:invoices") + "?status=OVERDUE"},
            {"label": "Payments", "url": "/finance/payments/"},
            {"label": "Suspense Queue", "url": "/finance/reconciliation/suspense/"},
        ],
    }
    dashboard_context = get_dashboard_context(request.user, "finance")
    dashboard_settings = dashboard_context.get("dashboard_settings", {})
    allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
    dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
    widget_meta_json = dashboard_context.get("widget_meta_json", "")
    available_sidebar_items = [
        {"id": "finance-home", "label": "Finance Home", "url": reverse("finance:dashboard"), "icon": "bi-cash-stack"},
        {"id": "finance-invoices", "label": "Invoices", "url": reverse("finance:invoices"), "icon": "bi-receipt"},
        {"id": "finance-payments", "label": "Payments", "url": reverse("finance:payments"), "icon": "bi-wallet2"},
        {"id": "finance-suspense", "label": "Suspense Queue", "url": reverse("finance:suspense_queue"), "icon": "bi-exclamation-triangle"},
        {"id": "finance-trial", "label": "Trial Balance", "url": reverse("finance:trial_balance"), "icon": "bi-bank"},
        {"id": "finance-reports", "label": "Reports", "url": reverse("finance:reports"), "icon": "bi-graph-up-arrow"},
    ]
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).order_by("-created_at")
    finance_request_link = reverse("requests:dashboard")

    # Chart data for dashboard visualizations
    status_counts = list(dashboard_data.get("status_counts") or [])
    trend = dashboard_data.get("trend") or []
    status_labels = dict(Invoice.Status.choices)
    chart_status_donut = {
        "type": "doughnut",
        "data": {
            "labels": [status_labels.get(sc["status"], sc["status"]) for sc in status_counts],
            "datasets": [{
                "data": [sc["count"] for sc in status_counts],
                "backgroundColor": [
                    "#6c757d", "#0d6efd", "#ffc107", "#198754", "#dc3545", "#adb5bd"
                ][: len(status_counts)],
            }],
        },
    }
    chart_trend_area = {
        "type": "line",
        "data": {
            "labels": [t["label"] for t in trend],
            "datasets": [{
                "label": "Invoice total",
                "data": [float(t["total"]) for t in trend],
                "fill": True,
                "borderColor": "#0d6efd",
                "backgroundColor": "rgba(13, 110, 253, 0.15)",
                "tension": 0.3,
            }],
        },
    }

    context = {
        "profile": profile,
        "hero": hero,
        "chart_status_donut_json": json.dumps(chart_status_donut),
        "chart_trend_area_json": json.dumps(chart_trend_area),
        **dashboard_data,
    }
    context.update({
        "allow_custom_layout": allow_custom_layout,
        "dashboard_settings": dashboard_settings,
        "dashboard_layout_url": dashboard_layout_url,
        "available_sidebar_items": available_sidebar_items,
        "widget_meta_json": widget_meta_json,
        "finance_requests_count": finance_requests_qs.count(),
        "finance_request_notifications": finance_requests_qs[:5],
        "finance_request_link": finance_request_link,
    })
    return render(request, "finance/dashboard.html", context)


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
    qs = Invoice.objects.filter(profile=profile).select_related(
        "student", "academic_year", "profile"
    ).prefetch_related(
        "payments",
        "student__guardian_links",
        Prefetch(
            "payer_shares",
            queryset=(
                InvoicePayerShare.objects.filter(is_active=True)
                .select_related("guardian", "guardian__guardian_user")
            ),
            to_attr="active_payer_shares",
        ),
    )
    
    # Filter invoices based on user role
    if request.user.role == User.Role.PARENT:
        # Parents can only see invoices for their children (respect opt-in)
        parent_students = _guardian_finance_qs(request.user).values_list('student_id', flat=True)
        qs = qs.filter(student_id__in=parent_students)
        if access_state["require_opt_in"] and not access_state["finance_count"]:
            qs = qs.none()
    elif not (request.user.is_staff or request.user.is_superuser or request.user.role == User.Role.ADMIN):
        return HttpResponseForbidden("You don't have permission to view invoices.")
    
    # Continue with existing filtering logic

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

    # Part B.4/B.6: sort order (data-agnostic)
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

    # Phase 18.2: One-click export (CSV). Cap 5000 rows; see docs/IMPROVEMENTS_EXECUTABLE_PLAN.md Phase 3.4.
    if request.GET.get("export") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Reference", "Type", "Status", "Due", "Student", "Total", "Balance", "Issued"])
        for inv in ordered_qs[:5000]:
            w.writerow([
                inv.reference or str(inv.id),
                inv.get_invoice_type_display(),
                inv.get_status_display(),
                inv.due_date.isoformat() if inv.due_date else "",
                str(inv.student) if inv.student_id else "",
                str(inv.total_amount),
                str(inv.balance_amount),
                inv.issued_date.isoformat() if inv.issued_date else "",
            ])
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="invoices_export.csv"'
        return resp

    # Phase 18.3: One-click export (PDF). Cap 500 rows for PDF; CSV uses 5000. See Phase 3.4 in plan.
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

    # Pagination: 25 per page (intentional limit; see docs/IMPROVEMENTS_EXECUTABLE_PLAN.md Phase 3.4).
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

    # Add split-billing summaries for list rendering without extra template logic.
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
                (share for share in shares if share.guardian.guardian_user_id == current_user_id),
                None,
            )
            if mine:
                inv.my_split_outstanding = mine.outstanding_amount
                inv.my_split_status = mine.get_status_display()

    return render(request, "finance/invoices.html", {
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
            if access_state["guardian_count"] else None
        ),
        "can_request_finance_access": access_state["allow_requests"] and access_state["require_opt_in"] and access_state["guardian_count"] > access_state["finance_count"],
        "finance_request_url": reverse("finance:finance_request_access"),
        "order_options": [
            ("-issued_date", "Date (newest first)"),
            ("issued_date", "Date (oldest first)"),
            ("-due_date", "Due date (latest first)"),
            ("due_date", "Due date (earliest first)"),
            ("-total_amount", "Amount (high to low)"),
            ("total_amount", "Amount (low to high)"),
        ],
        "selected_order": order_param or "-issued_date",
    })


@staff_member_required
def payment_list(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    qs = Payment.objects.filter(invoice__profile=profile).select_related(
        "invoice",
        "invoice__student",
        "invoice__academic_year",
    )

    # Part B.6: filters (data-agnostic; work with 0 or many rows)
    method = (request.GET.get("method") or "").strip()
    if method and method in [c[0] for c in PaymentMethodCode.choices]:
        qs = qs.filter(method=method)
    date_from = parse_date(request.GET.get("date_from") or "")
    date_to = parse_date(request.GET.get("date_to") or "")
    if date_from:
        qs = qs.filter(paid_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(paid_at__date__lte=date_to)

    # Part B.4/B.6: sort order (data-agnostic)
    _payment_order_map = {
        "paid_at": "paid_at",
        "-paid_at": "-paid_at",
        "amount": "amount",
        "-amount": "-amount",
    }
    order_param = (request.GET.get("order") or "").strip()
    order_by = _payment_order_map.get(order_param, "-paid_at")
    ordered_qs = qs.order_by(order_by)

    # Phase 18.2: One-click export (CSV). Cap 5000 rows; see docs/IMPROVEMENTS_EXECUTABLE_PLAN.md Phase 3.4.
    if request.GET.get("export") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Invoice", "Method", "Amount", "Paid at", "Student", "Receipt"])
        for pay in ordered_qs[:5000]:
            inv = pay.invoice
            w.writerow([
                inv.reference or str(inv.id),
                pay.get_method_display(),
                str(pay.amount),
                pay.paid_at.isoformat() if pay.paid_at else "",
                str(inv.student) if inv.student_id else "",
                pay.receipt_number or "",
            ])
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="payments_export.csv"'
        return resp

    # Phase 18.3: One-click export (PDF)
    if request.GET.get("export") == "pdf":
        try:
            from weasyprint import HTML
        except ImportError:
            return HttpResponse("PDF export requires WeasyPrint.", status=503)

        def _d(d):
            return d.strftime("%Y-%m-%d %H:%M") if d else ""

        # PDF export capped at 500 rows; CSV uses 5000. See Phase 3.4 in plan.
        rows_html = "".join(
            f"<tr><td>{pay.invoice.reference or pay.invoice_id}</td><td>{pay.get_method_display()}</td>"
            f"<td>{pay.amount}</td><td>{_d(pay.paid_at)}</td><td>{pay.invoice.student or ''}</td>"
            f"<td>{pay.receipt_number or ''}</td></tr>"
            for pay in ordered_qs[:500]
        )
        site = get_effective_site_settings(request=request)
        title = getattr(site, "site_name", None) or "Payments"
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

    # Pagination: 25 per page (intentional limit; see Phase 3.4 in plan).
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
    return render(request, "finance/payments.html", {
        "payments": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "pagination_extra_query": pagination_extra_query,
        "enable_ocr_scan_teller": enable_ocr_scan_teller,
        "payment_methods": PaymentMethodCode.choices,
        "selected_method": method or "",
        "date_from": request.GET.get("date_from") or "",
        "date_to": request.GET.get("date_to") or "",
        "order_options": [
            ("-paid_at", "Date (newest first)"),
            ("paid_at", "Date (oldest first)"),
            ("-amount", "Amount (high to low)"),
            ("amount", "Amount (low to high)"),
        ],
        "selected_order": order_param or "-paid_at",
    })


@staff_member_required
def cash_office_closure(request: HttpRequest):
    """
    Daily cash closure:
    - Recomputes cash collected from completed CASH payments for the selected day.
    - Stores opening cash, deposited amount, physical cash on hand, and discrepancy.
    """
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

    cash_collected = (
        Payment.objects.filter(
            invoice__profile=profile,
            method=PaymentMethodCode.CASH,
            status="completed",
            paid_at__date=closure_date,
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        or Decimal("0.00")
    )

    if request.method == "POST":
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
            return redirect("finance:cash_office_closure")
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

    recent_closures = CashOfficeClosure.objects.filter(profile=profile).order_by("-closure_date", "-updated_at")[:10]

    return render(
        request,
        "finance/cash_office_closure.html",
        {
            "form": form,
            "cash_collected": cash_collected,
            "expected_cash": expected_cash,
            "discrepancy_preview": discrepancy_preview,
            "recent_closures": recent_closures,
        },
    )


@staff_member_required
def split_allocation(request: HttpRequest):
    """
    Record a single payment split across fee types (Tuition, Sports, Workshop, etc.).
    Creates an invoice with multiple lines, one payment for the total, then applies
    payment and posts to OHADA ledger.
    """
    from apps.people.models import StudentProfile, StudentGuardian

    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    active_year = AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()
    if not active_year:
        return render(request, "finance/split_allocation.html", {
            "form": None,
            "error": "No active academic year. Set an academic year as active first.",
        })

    students = StudentProfile.objects.filter(academic_year=active_year).order_by("last_name", "first_name")
    selected_student_id = (request.POST.get("student") or request.GET.get("student") or "").strip()
    guardians = StudentGuardian.objects.none()
    if selected_student_id.isdigit():
        guardians = StudentGuardian.objects.filter(
            student_id=int(selected_student_id),
            student__academic_year=active_year,
            can_view_finance=True,
            guardian_user__is_active=True,
        ).select_related("guardian_user")

    form = SplitAllocationForm(
        request.POST or None,
        student_queryset=students,
        guardian_queryset=guardians,
    )

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
                StudentGuardian.objects.filter(
                    student=student,
                    can_view_finance=True,
                    guardian_user__is_active=True,
                ).select_related("guardian_user")
            )
            equal_parts = split_amount_equally(total_amount, len(student_guardians))
            payer_allocations = list(zip(student_guardians, equal_parts))

        with transaction.atomic():
            invoice = Invoice.objects.create(
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
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    return render(request, "finance/split_allocation.html", {
        "form": form,
        "active_year": active_year,
    })


@staff_member_required
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

    site = get_effective_site_settings(request=request)
    verification_method = getattr(site, "finance_receipt_verification_method", "pattern") or "pattern"
    ocr_runtime_status = get_ocr_runtime_status(
        verification_method,
        getattr(site, "marksheet_ocr_command", ""),
    )
    form = TellerScanForm(request.POST or None, request.FILES or None)

    extraction = None
    match_preview = None
    suspense_matches = []
    invoice_matches = []
    suggested_tolerance = Decimal(str(getattr(site, "finance_bank_verification_amount_tolerance", "1.00")))

    if request.method == "POST" and form.is_valid():
        if verification_method != "pattern" and not ocr_runtime_status.get("ready", False):
            messages.warning(
                request,
                "OCR runtime is not ready for the selected method. "
                "Extraction may fail until integration credentials/runtime are configured."
            )
        verifier = ReceiptVerificationService(
            verification_method=verification_method,
            marksheet_ocr_command=getattr(site, "marksheet_ocr_command", ""),
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
                    status__in=[SuspensePayment.Status.OPEN, SuspensePayment.Status.PARTIAL],
                    amount__gte=low,
                    amount__lte=high,
                )
                .select_related("bank_statement_entry", "suggested_student")
                .order_by("-created_at")[:8]
            )

            invoice_qs = Invoice.objects.select_related("student").filter(
                profile=profile,
                status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL, Invoice.Status.OVERDUE],
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


SESSION_KEY_LAST_GENERATED_INVOICE_IDS = "finance_last_generated_invoice_ids"


@staff_member_required
def generate_fees(request: HttpRequest):
    profile = _active_profile(request)
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
        request.session[SESSION_KEY_LAST_GENERATED_INVOICE_IDS] = [inv.id for inv in invoices]
        messages.success(request, f"Generated {len(invoices)} invoices. You can notify guardians below.")
        return redirect("finance:generate_fees")

    invoice_ids = request.session.get(SESSION_KEY_LAST_GENERATED_INVOICE_IDS) or []
    return render(request, "finance/generate_fees.html", {
        "plans": plans,
        "last_generated_invoice_ids": invoice_ids,
        "last_generated_count": len(invoice_ids),
    })


@staff_member_required
@require_POST
def notify_guardians_new_invoices(request: HttpRequest):
    """Phase 4.1: Send new-invoice notifications to guardians for the last bulk-generated invoices."""
    invoice_ids = request.session.pop(SESSION_KEY_LAST_GENERATED_INVOICE_IDS, None) or []
    if not invoice_ids:
        messages.info(request, "No recent invoices to notify. Generate invoices first.")
        return redirect("finance:generate_fees")
    total = notify_guardians_new_invoices_bulk(
        invoice_ids,
        created_by=request.user,
        send_email=getattr(get_effective_site_settings(request=request), "finance_notify_new_invoice_email", False),
    )
    messages.success(request, f"Notifications sent to {total} guardian(s) for the new invoices.")
    return redirect("finance:invoices")


@staff_member_required
def trial_balance(request: HttpRequest):
    profile = _active_profile(request)
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
        is_guardian = bool(invoice.student_id and StudentGuardian.objects.filter(
            guardian_user=request.user,
            student_id=invoice.student_id,
        ).exists())
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
                    "can_request_finance_access": access_state["allow_requests"] and access_state["require_opt_in"],
                    "finance_request_url": reverse("finance:invoice_request_access", args=[invoice.id]),
                },
                status=403,
            )
        return HttpResponseForbidden("You don't have permission to view this invoice.")

    if request.method == "POST" and request.FILES.get("attachment"):
        from apps.accounts.validators import FileTypeValidator, FileSizeValidator
        from django.core.exceptions import ValidationError
        up = request.FILES["attachment"]
        try:
            FileTypeValidator(
                allowed_extensions=[".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods"],
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
            messages.error(request, e.messages[0] if getattr(e, "messages", None) else str(e))
            return redirect("finance:invoice_detail", invoice_id=invoice.id)
        invoice.attachment = up
        invoice.save(update_fields=["attachment"])
        messages.success(request, "Attachment uploaded.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    payment_link = generate_payment_link(invoice)
    reminder = getattr(invoice, "reminder", None)
    
    # Get reminder history (last 10 logs)
    reminder_logs = []
    if reminder:
        reminder_logs = reminder.logs.order_by("-sent_at")[:10]

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
            invoice.payer_shares.filter(is_active=True).select_related("guardian", "guardian__guardian_user")
        )
        if payer_shares:
            current_guardian_share = next(
                (
                    share
                    for share in payer_shares
                    if share.guardian.guardian_user_id == getattr(request.user, "id", None)
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

    # Get payment proof uploads for this invoice
    payment_proof_uploads = PaymentProofUpload.objects.filter(
        invoice=invoice
    ).select_related("uploaded_by", "verified_by", "payment").order_by("-created_at")
    
    return render(request, "finance/invoice_detail.html", {
        "invoice": invoice,
        "payment_link": payment_link,
        "reminder": reminder,
        "payment_proof_uploads": payment_proof_uploads,
        "finance_access_required": access_state["require_opt_in"],
        "finance_access_granted": access_state["finance_count"] > 0,
        "finance_access_summary": finance_summary,
        "can_request_finance_access": access_state["allow_requests"] and access_state["require_opt_in"] and access_state["guardian_count"] > access_state["finance_count"],
        "finance_request_url": reverse("finance:invoice_request_access", args=[invoice.id]),
        "finance_guardian_count": access_state["finance_count"],
        "guardian_link_count": access_state["guardian_count"],
        "guardian_share": guardian_share,
        "payer_share_count": len(payer_shares),
    })


@login_required
@require_POST
def upload_payment_receipt(request: HttpRequest, invoice_id: int):
    """
    Allow parents/guardians to upload payment receipts for cash/bank payments.
    Receipts are automatically verified and payments applied if verification passes.
    """
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
    
    # Check permission
    can_view = can_view_invoice(request.user, invoice_id)
    if not can_view:
        is_parent = getattr(request.user, "role", "") == User.Role.PARENT
        is_guardian = bool(invoice.student_id and StudentGuardian.objects.filter(
            guardian_user=request.user,
            student_id=invoice.student_id,
        ).exists())
        if not (is_parent and is_guardian):
            return HttpResponseForbidden("You don't have permission to upload receipts for this invoice.")
    
    # Check if invoice is already paid
    if invoice.status == Invoice.Status.PAID:
        messages.error(request, "This invoice is already fully paid.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    
    # Resolve receipt upload policy through the owner-scoped finance runtime config.
    site_settings = get_effective_site_settings(request=request)
    finance_runtime = (
        site_settings.get_finance_runtime_config()
        if callable(getattr(site_settings, "get_finance_runtime_config", None))
        else {}
    )
    if not finance_runtime.get("receipt_upload_enabled", getattr(site_settings, "finance_receipt_upload_enabled", True)):
        messages.error(request, "Receipt upload is currently disabled.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    
    # Validate file upload
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
            f"Maximum allowed is {max_mb} MB. Please compress or use a smaller image."
        )
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    allowed_ext = (
        finance_runtime.get(
            "receipt_allowed_extensions",
            getattr(site_settings, "finance_receipt_allowed_extensions", "pdf,jpg,jpeg,png"),
        )
        or "pdf,jpg,jpeg,png"
    ).strip().lower()
    allowed_list = [e.strip().lstrip(".") for e in allowed_ext.split(",") if e.strip()]
    ext = (receipt_file.name or "").split(".")[-1].lower() if "." in (receipt_file.name or "") else ""
    if allowed_list and ext not in allowed_list:
        messages.error(
            request,
            f"File type '.{ext}' is not allowed. Use: {', '.join('.' + e for e in allowed_list)}. "
            "Please upload a PDF or image (e.g. photo of receipt)."
        )
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    
    # Get payment method
    payment_method = request.POST.get("payment_method", "")
    if payment_method not in [code[0] for code in PaymentMethodCode.choices]:
        messages.error(request, "Invalid payment method.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    
    # Get optional fields
    transaction_reference = request.POST.get("transaction_reference", "").strip()
    idempotency_key = (request.POST.get("idempotency_key", "") or "").strip()[:64]
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = (forwarded_for.split(",")[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR", "")) or None
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
    
    # Run fraud detection BEFORE creating record
    fraud_detector = ReceiptFraudDetector()
    receipt_date = None  # Will be extracted during verification
    fraud_result = fraud_detector.detect_fraud(
        receipt_file=receipt_file,
        receipt_date=receipt_date,
        transaction_reference=transaction_reference,
        uploaded_by_id=request.user.id,
        invoice_id=invoice.id,
        uploaded_amount=uploaded_amount,
        ip_address=ip_address,
        user_agent=user_agent
    )
    file_hash = fraud_result.get("file_hash", "")

    # Duplicate check by file hash (same invoice + user within window)
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
                "This receipt was already received (same file). If payment was deducted but you saw an error, do not pay again; contact finance with your transaction reference."
            )
            return redirect("finance:invoice_detail", invoice_id=invoice.id)
    
    # Create PaymentProofUpload record with fraud detection data
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
        flagged_at=timezone.now() if fraud_result["recommendation"] in ["review", "reject"] else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    # If suspicious, notify finance staff immediately
    if proof_upload.is_suspicious:
        _notify_finance_staff_suspicious_receipt(proof_upload, fraud_result)
    
    # Trigger automatic verification (if enabled)
    if finance_runtime.get(
        "receipt_auto_verify_enabled",
        getattr(site_settings, "finance_receipt_auto_verify_enabled", True),
    ):
        from apps.finance.tasks import process_payment_receipt_upload_task
        school_id = str(getattr(invoice, "school_id", None) or getattr(getattr(invoice, "student", None), "school_id", None) or "")
        process_payment_receipt_upload_task.delay(proof_upload.id, school_id=school_id if school_id else None)
        messages.success(
            request,
            "Receipt uploaded successfully. It is being verified automatically. "
            "You will be notified once verification is complete."
        )
    else:
        messages.success(
            request,
            "Receipt uploaded successfully. It will be reviewed by finance staff."
        )
    
    return redirect("finance:invoice_detail", invoice_id=invoice.id)


@login_required
def resend_reminder(request: HttpRequest, invoice_id: int) -> HttpResponse:
    """Resend payment reminder immediately for an invoice."""
    from apps.accounts.permissions import can_view_invoice
    from apps.finance.tasks import run_payment_reminders
    from django.utils import timezone
    
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    # Permission check: staff or parent/guardian
    if not request.user.is_staff:
        can_view = can_view_invoice(request.user, invoice_id)
        if not can_view:
            return HttpResponseForbidden("You don't have permission to resend reminders for this invoice.")
    
    reminder = getattr(invoice, "reminder", None)
    if not reminder:
        messages.error(request, "No reminder configured for this invoice.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    
    if not reminder.is_active:
        messages.warning(request, "Reminder is inactive. Activate it first to resend.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)
    
    # Force send now by setting next_send_at to past
    reminder.next_send_at = timezone.now() - timedelta(minutes=1)
    reminder.save(update_fields=["next_send_at"])
    
    # Run reminder task synchronously (or queue it)
    try:
        result = run_payment_reminders()
        sent_count = result.get("sent", 0)
        if sent_count > 0:
            messages.success(
                request,
                f"Reminder sent successfully ({sent_count} channel(s): {', '.join(result.get('channels', {}).keys())})."
            )
        else:
            messages.info(request, "Reminder queued but no sends occurred (may have been sent recently or no guardians configured).")
    except FINANCE_SOFT_FAILURES as e:
        logger.error("Error resending reminder: %s", str(e))
        messages.error(request, f"Error resending reminder: {str(e)}")
    
    return redirect("finance:invoice_detail", invoice_id=invoice.id)


def _notify_finance_staff_suspicious_receipt(proof_upload: PaymentProofUpload, fraud_result: dict) -> None:
    """Notify finance staff when suspicious receipt is uploaded."""
    from apps.accounts.models import User
    from apps.evals.notifications import NotificationService
    
    try:
        # Get finance staff (users with finance permissions)
        finance_staff = User.objects.filter(
            is_staff=True,
            groups__name__in=["Finance", "Bursar", "Accountant"]
        ).distinct()
        
        # If no specific finance group, notify all staff
        if not finance_staff.exists():
            finance_staff = User.objects.filter(is_staff=True, is_superuser=False)
        
        notification_service = NotificationService()
        
        fraud_flags_str = ", ".join(fraud_result.get("fraud_flags", []))
        message = (
            f"⚠️ SUSPICIOUS RECEIPT UPLOADED\n\n"
            f"Invoice: {proof_upload.invoice.reference or proof_upload.invoice.id}\n"
            f"Student: {proof_upload.invoice.student}\n"
            f"Uploaded by: {proof_upload.uploaded_by.get_full_name() if proof_upload.uploaded_by else 'Unknown'}\n"
            f"Amount: {proof_upload.uploaded_amount or 'Not specified'}\n"
            f"Fraud Risk Score: {fraud_result.get('fraud_risk_score', 0)}/100\n"
            f"Flags: {fraud_flags_str}\n"
            f"Recommendation: {fraud_result.get('recommendation', 'review').upper()}\n\n"
            f"Please review immediately: /admin/finance/paymentproofupload/{proof_upload.id}/change/"
        )
        
        for staff_member in finance_staff[:10]:  # Limit to 10 staff to avoid spam
            try:
                notification_service.send_notification(
                    user=staff_member,
                    title="🚨 Suspicious Receipt Upload",
                    message=message,
                    channels=["email"],  # Always email for critical alerts
                )
            except FINANCE_SOFT_FAILURES as e:
                logger.error(f"Failed to notify finance staff {staff_member.id}: {str(e)}")
    
    except FINANCE_SOFT_FAILURES as e:
        logger.error(f"Error notifying finance staff about suspicious receipt: {str(e)}")


@login_required
@require_POST
def request_finance_access(request: HttpRequest, invoice_id: int | None = None):
    """
    Allow guardians to request finance visibility from admins/finance.
    Sends internal messages and finance notifications to admin-aligned roles.
    """
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian, StudentProfile

    flags = _backend_flags(request)
    if not flags.get("allow_finance_access_requests", True):
        return HttpResponseForbidden("Finance access requests are disabled by the administrator.")

    role = getattr(request.user, "role", "")
    is_staff_like = request.user.is_staff or request.user.is_superuser
    if role != User.Role.PARENT and not is_staff_like:
        return HttpResponseForbidden("Only guardians or staff can manage finance access.")

    # Staff can directly grant finance access for a student's guardians
    if is_staff_like and request.method == "POST" and request.POST.get("student_id"):
        try:
            student_id = int(request.POST.get("student_id"))
        except (TypeError, ValueError):
            messages.error(request, "Invalid student selection.")
            return redirect(request.META.get("HTTP_REFERER", reverse("finance:invoices")))

        student = StudentProfile.objects.filter(id=student_id).first()
        if not student:
            messages.error(request, "Student not found.")
            return redirect(request.META.get("HTTP_REFERER", reverse("finance:invoices")))

        guardians = StudentGuardian.objects.filter(student=student).select_related("guardian_user")
        to_grant = guardians.filter(can_view_finance=False)
        updated = to_grant.update(can_view_finance=True)

        from apps.requests.services import create_access_request
        access_request = create_access_request(
            request_type="FINANCE_ACCESS",
            requester=request.user,
            title="Finance access granted (staff)",
            summary=f"Staff granted finance access for {student}.",
            details={
                "student_id": student.id,
                "student_name": str(student),
                "granted_links": updated,
            },
            status="APPROVED",
            school=getattr(request, "school", None),
        )
        access_request.add_audit(
            "auto_grant",
            actor=request.user,
            message="Finance access granted by staff action.",
            details={"student_id": student.id, "updated_links": updated},
        )

        notifier = NotificationService()
        site = get_effective_site_settings(request=request)
        channels = getattr(site, "notification_channels", []) or []
        from_email = getattr(site, "email_from_address", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)

        messages_out = []
        for link in guardians:
            user = link.guardian_user
            if not user:
                continue
            _create_finance_request_notification(
                user,
                title="Finance access granted",
                message=f"Finance access was enabled for {student}.",
                severity=Notification.Severity.INFO,
                created_by=request.user,
                action="grant_access",
                details=f"Auto-granted finance visibility for {student}.",
            )
            messages_out.append(Message(
                sender=request.user,
                recipient=user,
                subject="Finance access granted",
                body=f"You can now view finance records for {student}.",
            ))
            if "sms" in channels:
                phone = (
                    getattr(user, "phone", None)
                    or getattr(user, "phone_number", None)
                    or getattr(getattr(user, "profile", None), "phone", None)
                )
                if phone:
                    try:
                        notifier.send_sms(phone, f"Finance access granted for {student}.")
                    except FINANCE_SOFT_FAILURES:
                        logger.exception("Failed to send finance access SMS.")
            if "email" in channels and from_email and user.email:
                try:
                    send_mail(
                        subject="Finance access granted",
                        message=f"You can now view finance records for {student}.",
                        from_email=from_email,
                        recipient_list=[user.email],
                    )
                except FINANCE_SOFT_FAILURES:
                    logger.exception("Failed to send finance access email.")

        if messages_out:
            Message.objects.bulk_create(messages_out)

        messages.success(request, f"Updated {updated} guardian link(s) for {student}.")
        return redirect(request.META.get("HTTP_REFERER", reverse("finance:invoices")))

    guardian_links = StudentGuardian.objects.filter(guardian_user=request.user).select_related("student")
    if request.method == "POST" and request.POST.get("student_id"):
        try:
            student_id = int(request.POST.get("student_id"))
        except (TypeError, ValueError):
            student_id = None
        if student_id and guardian_links.filter(student_id=student_id).exists():
            guardian_links = guardian_links.filter(student_id=student_id)
    if not guardian_links.exists():
        messages.error(request, "Link a student first to route your request.")
        return redirect(request.META.get("HTTP_REFERER", reverse("finance:invoices")))

    invoice_ref = None
    if invoice_id:
        invoice = Invoice.objects.filter(id=invoice_id).select_related("student").first()
        if not invoice:
            return HttpResponseForbidden("Invoice not found.")
        if invoice.student_id and not guardian_links.filter(student_id=invoice.student_id).exists():
            return HttpResponseForbidden("You can only request access for your linked students.")
        invoice_ref = invoice.reference or str(invoice.id)

    recipients = User.objects.filter(
        models.Q(role__in=[
            User.Role.ADMIN,
            User.Role.BURSAR,
            User.Role.LEADERSHIP,
            User.Role.IT_ADMIN,
            User.Role.SUPERADMIN,
        ]) | models.Q(is_superuser=True)
    ).distinct()

    if not recipients.exists():
        messages.warning(
            request,
            "No admin recipients were found to notify. Please contact the school directly.",
        )
        return redirect(request.META.get("HTTP_REFERER", reverse("finance:invoices")))

    student_names = ", ".join(str(link.student) for link in guardian_links)
    subject = "Finance access request"
    body_lines = [
        f"Guardian {request.user.get_full_name() or request.user.username} ({request.user.email}) requested finance access.",
        f"Linked students: {student_names or 'None'}",
    ]
    if invoice_ref:
        body_lines.append(f"Reference invoice: {invoice_ref}")
    body_lines.append(f"Finance opt-in required: {'Yes' if flags.get('require_guardian_finance_opt_in') else 'No'}")
    body = "\n".join(body_lines)

    from apps.requests.services import create_access_request
    access_request = create_access_request(
        request_type="FINANCE_ACCESS",
        requester=request.user,
        title="Finance access request",
        summary=f"Guardian requested finance access for {student_names or 'linked students'}",
        details={
            "student_ids": [link.student_id for link in guardian_links],
            "student_names": student_names,
            "invoice_ref": invoice_ref,
            "require_opt_in": bool(flags.get("require_guardian_finance_opt_in")),
        },
        school=getattr(request, "school", None),
    )
    access_request.add_audit(
        "notify_admins",
        actor=request.user,
        message="Finance access request submitted.",
        details={"recipients": [r.id for r in recipients]},
    )

    messages_created = [
        Message(sender=request.user, recipient=recipient, subject=subject, body=body)
        for recipient in recipients
    ]
    Message.objects.bulk_create(messages_created)

    request_details = (
        f"Students: {student_names or 'None'}; "
        f"Invoice: {invoice_ref or 'N/A'}; "
        f"Opt-in required: {'Yes' if flags.get('require_guardian_finance_opt_in') else 'No'}"
    )
    for recipient in recipients:
        _create_finance_request_notification(
            recipient,
            title="Finance access request",
            message=f"{request.user.get_full_name() or request.user.username} requested finance access.",
            severity=Notification.Severity.ALERT,
            created_by=request.user,
            action="request_sent",
            details=request_details,
        )

    # Optional email/SMS alerts based on site notification channels
    site = get_effective_site_settings(request=request)
    channels = getattr(site, "notification_channels", []) or []
    from_email = getattr(site, "email_from_address", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if "email" in channels and from_email:
        recipient_emails = [r.email for r in recipients if r.email]
        if recipient_emails:
            try:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=from_email,
                    recipient_list=recipient_emails,
                )
            except FINANCE_SOFT_FAILURES:
                logger.exception("Failed to send finance access email notification.")

    if "sms" in channels:
        notifier = NotificationService()
        for recipient in recipients:
            phone = (
                getattr(recipient, "phone", None)
                or getattr(recipient, "phone_number", None)
                or getattr(getattr(recipient, "profile", None), "phone", None)
            )
            if phone:
                try:
                    notifier.send_sms(phone, f"Finance access request from {request.user.get_full_name() or request.user.username}.")
                except FINANCE_SOFT_FAILURES:
                    logger.exception("Failed to send finance access SMS notification.")

    # Notify requesting guardian for confirmation if access already granted
    if guardian_links.filter(can_view_finance=True).exists():
        _create_finance_request_notification(
            request.user,
            title="Finance access already enabled",
            message="Finance access is already enabled for your linked students.",
            severity=Notification.Severity.INFO,
            created_by=None,
            action="info_already_enabled",
            details=f"Existing access for {student_names or 'linked students'}.",
        )
        Message.objects.create(
            sender=request.user,
            recipient=request.user,
            subject="Finance access confirmation",
            body="Finance access is already enabled for your linked students. You can view invoices now.",
        )

    messages.success(request, "Request sent to the admin/finance team.")
    return redirect(request.META.get("HTTP_REFERER", reverse("finance:invoices")))


@staff_member_required
def finance_access_bulk(request: HttpRequest):
    """
    Staff page to bulk-grant guardian finance access by year/class with audit-friendly notifications.
    """
    from apps.academics.models import AcademicYear, Classroom
    from apps.people.models import StudentGuardian

    years = AcademicYear.objects.order_by("-start_date")
    classrooms = Classroom.objects.select_related("academic_year").order_by("name")

    selected_year = request.POST.get("year") or request.GET.get("year") or ""
    selected_class = request.POST.get("classroom") or request.GET.get("classroom") or ""

    guardians = StudentGuardian.objects.select_related("guardian_user", "student")
    if selected_year:
        guardians = guardians.filter(student__academic_year_id=selected_year)
    if selected_class:
        guardians = guardians.filter(student__classroom_id=selected_class)

    pending_qs = guardians.filter(can_view_finance=False)
    pending_count = pending_qs.count()
    granted = 0

    flags = _backend_flags(request)
    site = get_effective_site_settings(request=request)
    channels = getattr(site, "notification_channels", []) or []
    from_email = getattr(site, "email_from_address", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    notifier = NotificationService()

    if request.method == "POST":
        # Materialize list before update so notifications run (pending_qs would be empty after update)
        pending_list = list(pending_qs.select_related("guardian_user", "student"))
        with transaction.atomic():
            granted = pending_qs.update(can_view_finance=True)

        messages_out = []
        if granted and pending_list:
            for link in pending_list:
                user = link.guardian_user
                if not user:
                    continue
                _create_finance_request_notification(
                    user,
                    title="Finance access granted",
                    message=f"Finance access was enabled for {link.student}.",
                    severity=Notification.Severity.INFO,
                    created_by=request.user,
                    action="grant_access_bulk",
                    details=f"Bulk access granted for {link.student}.",
                )
                messages_out.append(Message(
                    sender=request.user,
                    recipient=user,
                    subject="Finance access granted",
                    body=f"You can now view finance records for {link.student}.",
                ))
                if "sms" in channels:
                    phone = (
                        getattr(user, "phone", None)
                        or getattr(user, "phone_number", None)
                        or getattr(getattr(user, "profile", None), "phone", None)
                    )
                    if phone:
                        try:
                            notifier.send_sms(phone, f"Finance access granted for {link.student}.")
                        except FINANCE_SOFT_FAILURES:
                            logger.exception("Failed to send finance access SMS.")
                if "email" in channels and from_email and user.email:
                    try:
                        send_mail(
                            subject="Finance access granted",
                            message=f"You can now view finance records for {link.student}.",
                            from_email=from_email,
                            recipient_list=[user.email],
                        )
                    except FINANCE_SOFT_FAILURES:
                        logger.exception("Failed to send finance access email.")

        if messages_out:
            Message.objects.bulk_create(messages_out)

        logger.info(
            "Bulk finance access grant by %s: granted=%s pending_before=%s year=%s class=%s",
            request.user,
            granted,
            pending_count,
            selected_year,
            selected_class,
        )
        messages.success(request, f"Granted finance access to {granted} guardian link(s).")
        return redirect(request.path + f"?year={selected_year}&classroom={selected_class}")

    context = {
        "years": years,
        "classrooms": classrooms,
        "selected_year": selected_year,
        "selected_class": selected_class,
        "pending_count": pending_count,
        "total_links": guardians.count(),
        "require_opt_in": flags.get("require_guardian_finance_opt_in"),
    }
    return render(request, "finance/access_bulk.html", context)


@staff_member_required
def invoice_receipt(request: HttpRequest, invoice_id: int, payment_id: int | None = None):
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
    html = render_to_string("finance/receipt.html", context)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="receipt-{payment.id}.pdf"'
    return response


@csrf_exempt
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
    
    def _provider_code() -> str:
        configured = normalize_provider_slug((integration.config or {}).get("provider_slug")) if integration else ""
        return configured or normalize_provider_slug(provider_slug) or (provider_slug or "").strip().lower()

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
            _first_present(payload, ["reference", "payment_reference", "transaction_id", "transactionId", "external_reference", "txid", "id"])
            or _first_present(data_block, ["reference", "payment_reference", "transaction_id", "transactionId", "external_reference", "txid", "id"])
            or _first_present(txn_block, ["reference", "payment_reference", "transaction_id", "transactionId", "external_reference", "txid", "id"])
            or _first_present(metadata, ["reference", "payment_reference", "transaction_id", "transactionId", "external_reference", "txid"])
        )
        return str(value or "").strip()

    def _extract_invoice_id(payload: dict) -> int | None:
        metadata = _as_dict(payload.get("metadata"))
        data_block = _as_dict(payload.get("data"))
        candidates = [
            _first_present(payload, ["invoice_id", "invoice", "invoiceId", "invoiceID"]),
            _first_present(data_block, ["invoice_id", "invoice", "invoiceId", "invoiceID"]),
            _first_present(metadata, ["invoice_id", "invoice", "invoiceId", "invoiceID"]),
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
            or _first_present(data_block, ["amount", "paid_amount", "transaction_amount"])
            or _first_present(txn_block, ["amount", "paid_amount", "transaction_amount"])
            or _first_present(metadata, ["amount", "paid_amount", "transaction_amount"])
        )

    def _extract_method(payload: dict, provider_code: str) -> str:
        raw_method = _first_present(payload, ["method", "payment_method", "channel"]) or ""
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
        return PROVIDER_SLUG_TO_METHOD.get(provider_code) or PROVIDER_SLUG_TO_METHOD.get(provider_slug) or PaymentMethodCode.MTN_MOMO

    def _request_content_type() -> str:
        return ((request.content_type or request.META.get("CONTENT_TYPE") or "").split(";", 1)[0]).strip().lower()

    def _content_type_is_json() -> bool:
        content_type = _request_content_type()
        return content_type == "application/json" or content_type.endswith("+json")

    integration = get_payment_integration_by_slug(provider_slug)
    if not integration:
        logger.warning(f"Webhook request for unknown provider: {provider_slug}")
        return HttpResponseForbidden("Unknown provider.")

    provider_code = _provider_code()
    validator = WebhookSecurityValidator(integration.config or {})
    client_ip = validator.get_client_ip(request)
    request_body = b""

    def _request_body_excerpt(raw_body: bytes | None = None) -> str:
        body = request_body if raw_body is None else raw_body
        return body.decode("utf-8", errors="replace")[:500]

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
        payload: dict[str, object] = {
            "provider": provider_code,
            "reference_id": reference_id,
            "client_ip": client_ip,
            "signature_valid": signature_valid,
            "status": status,
            "request_body": _request_body_excerpt(),
        }
        if response_status is not None:
            payload["response_status"] = response_status
        if invoice is not None:
            payload["invoice"] = invoice
        if payment is not None:
            payload["payment"] = payment
        if error_message:
            payload["error_message"] = error_message
        return WebhookLog.objects.create(**payload)

    request_body = request.body
    if request_body and not _content_type_is_json():
        _create_webhook_log(
            reference_id="unknown",
            status=WebhookLog.Status.INVALID,
            response_status=415,
            error_message=f"Unsupported content type: {_request_content_type() or 'unknown'}",
        )
        return HttpResponse("Content-Type must be application/json.", status=415)

    try:
        data = json.loads(request_body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Invalid webhook payload from {provider_slug}: {e}")
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

    reference_id = _extract_reference(data) or "unknown"

    # Step 1: IP whitelist check
    if not validator.validate_ip_whitelist(client_ip):
        _create_webhook_log(
            reference_id=reference_id,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message=f"IP not whitelisted: {client_ip}",
        )
        logger.warning(f"Rejected webhook from unauthorized IP {client_ip} for {provider_slug}")
        return HttpResponseForbidden("IP not whitelisted.")

    # Step 2: Rate limiting check
    if not validator.validate_rate_limit(client_ip):
        _create_webhook_log(
            reference_id=reference_id,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message=f"Rate limit exceeded for IP {client_ip}",
        )
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
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=False,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message="Invalid HMAC signature",
        )
        logger.warning(f"Invalid signature from {provider_slug} ({client_ip})")
        return HttpResponseForbidden("Invalid signature.")

    # Step 4: Optional timestamp replay protection
    timestamp_header = integration.config.get("timestamp_header", "X-Timestamp") if integration.config else "X-Timestamp"
    request_timestamp = (
        request.headers.get(timestamp_header)
        or request.META.get(f"HTTP_{timestamp_header.upper().replace('-', '_')}")
    )
    if not validator.validate_timestamp(request_timestamp):
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=403,
            error_message="Invalid or stale webhook timestamp",
        )
        logger.warning(f"Invalid timestamp from {provider_slug} ({client_ip})")
        return HttpResponseForbidden("Invalid timestamp.")

    # Step 5: Idempotency check (prevent duplicate payments)
    if not validator.validate_idempotency(provider_code, reference_id):
        webhook_log = _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.DUPLICATE,
            response_status=200,
        )
        logger.info(f"Duplicate webhook from {provider_slug}: {reference_id}")
        return JsonResponse({"status": "ignored", "reason": "duplicate"})

    # Step 6: Extract and validate payment data
    invoice_id = _extract_invoice_id(data)
    amount = _extract_amount(data)
    method = _extract_method(data, provider_code)

    # Validate amount
    is_valid, error_msg = PaymentValidator.validate_amount(amount)
    if not is_valid:
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=400,
            error_message=f"Invalid amount: {error_msg}",
        )
        logger.warning(f"Invalid payment amount from {provider_slug}: {amount}")
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

    # Step 7: Fetch invoice
    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        _create_webhook_log(
            reference_id=reference_id,
            signature_valid=True,
            status=WebhookLog.Status.INVALID,
            response_status=400,
            error_message=f"Invoice {invoice_id} not found",
        )
        logger.warning(f"Invoice {invoice_id} not found from webhook {provider_slug}")
        return HttpResponseBadRequest(f"Invoice {invoice_id} not found.")

    # Step 8: Validate amount against invoice balance
    invoice_paid = sum(invoice.payments.values_list("amount", flat=True)) or Decimal("0")
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
        logger.warning(f"Payment amount validation failed for invoice {invoice_id}: {error_msg}")
        return HttpResponseBadRequest(error_msg)

    # Step 9: Record payment within transaction (atomic)
    try:
        with transaction.atomic():
            # Create WebhookLog first (in PROCESSING state)
            webhook_log = _create_webhook_log(
                reference_id=reference_id,
                signature_valid=True,
                status=WebhookLog.Status.PROCESSING,
                invoice=invoice,
            )

            # Record the payment
            payment = record_provider_payment(
                invoice=invoice,
                amount=amount,
                method=method or PaymentMethodCode.MTN_MOMO,
                reference=_extract_reference(data),
                external_reference=reference_id,
            )

            if not payment:
                webhook_log.status = WebhookLog.Status.FAILED
                webhook_log.error_message = "Failed to create payment record"
                webhook_log.response_status = 500
                webhook_log.save(update_fields=["status", "error_message", "response_status"])
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

    except FINANCE_SOFT_FAILURES as e:
        # Handle any transaction errors
        logger.exception(f"Transaction error processing webhook {reference_id}: {e}")
        try:
            webhook_log = WebhookLog.objects.get(reference_id=reference_id, provider=provider_code)
            webhook_log.status = WebhookLog.Status.FAILED
            webhook_log.error_message = f"Transaction error: {str(e)[:200]}"
            webhook_log.response_status = 500
            webhook_log.save(update_fields=["status", "error_message", "response_status"])
        except WebhookLog.DoesNotExist:
            _create_webhook_log(
                reference_id=reference_id,
                signature_valid=True,
                status=WebhookLog.Status.FAILED,
                response_status=500,
                error_message=f"Transaction error: {str(e)[:200]}",
            )
        return JsonResponse({"status": "error", "reason": "processing_failed"}, status=500)


@staff_member_required
def notifications(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    qs = Notification.objects.filter(
        models.Q(recipient=request.user) | models.Q(created_by=request.user)
    ).order_by("-created_at")
    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()
    return render(request, "finance/notifications.html", {
        "alerts": page_obj.object_list,
        "page_obj": page_obj,
        "pagination_extra_query": pagination_extra_query,
    })


@staff_member_required
def finance_requests(request: HttpRequest):
    base_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
    )
    view_mode = request.GET.get("view", "all")
    severity_filter = (request.GET.get("severity", "all") or "all").upper()
    filtered_qs = base_qs.order_by("-created_at")
    if severity_filter != "ALL":
        filtered_qs = filtered_qs.filter(severity=severity_filter)
    if view_mode == "unread":
        notifications_qs = filtered_qs.filter(is_read=False)
    else:
        notifications_qs = filtered_qs

    unread_count = base_qs.filter(is_read=False).count()
    severity_counts = (
        base_qs
        .values("severity")
        .order_by("severity")
        .annotate(count=Count("id"))
    )
    severity_counts_dict = {row["severity"]: row["count"] for row in severity_counts}
    severity_options = [
        {"key": "ALL", "label": "All", "param": "all", "count": severity_counts_dict.get("ALL", 0)},
        {"key": "INFO", "label": "Info", "param": "info", "count": severity_counts_dict.get("INFO", 0)},
        {"key": "WARNING", "label": "Warning", "param": "warning", "count": severity_counts_dict.get("WARNING", 0)},
        {"key": "ALERT", "label": "Alert", "param": "alert", "count": severity_counts_dict.get("ALERT", 0)},
    ]

    if request.method == "POST":
        if request.POST.get("mark_all_unread"):
            targets = list(base_qs.filter(is_read=False))
            if targets:
                Notification.objects.filter(id__in=[n.id for n in targets]).update(is_read=True)
                for notif in targets:
                    FinanceRequestAudit.objects.create(
                        notification=notif,
                        user=request.user,
                        action="marked_read",
                        details="Marked all unread from finance inbox.",
                    )
                messages.success(request, f"Marked {len(targets)} finance request(s) as read.")
            return redirect(f"{reverse('finance:requests')}?view={view_mode}&severity={severity_filter.lower()}")

        selected = request.POST.getlist("notification_id")
        if selected:
            targets = list(base_qs.filter(id__in=selected))
            if targets:
                Notification.objects.filter(id__in=[n.id for n in targets]).update(is_read=True)
                for notif in targets:
                    FinanceRequestAudit.objects.create(
                        notification=notif,
                        user=request.user,
                        action="marked_read",
                        details="Marked read from finance requests dashboard.",
                    )
                messages.success(request, f"Marked {len(targets)} finance request(s) as read.")
        return redirect(f"{reverse('finance:requests')}?view={view_mode}&severity={severity_filter.lower()}")

    per_page = min(100, max(10, int(request.GET.get("page_size", 25))))
    paginator = Paginator(notifications_qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()

    return render(request, "finance/requests.html", {
        "notifications": page_obj.object_list,
        "page_obj": page_obj,
        "unread_count": unread_count,
        "view_mode": view_mode,
        "severity_filter": severity_filter,
        "severity_counts": {row["severity"]: row["count"] for row in severity_counts},
        "severity_options": severity_options,
        "pagination_extra_query": pagination_extra_query,
        "finance_request_audits": list(
            FinanceRequestAudit.objects.select_related("notification", "user").order_by("-created_at")[:25]
        ),
    })


def _can_access_accounting(user):
    """Accountant role or accounting.view permission (for Bursar entries report, expense vs budget)."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    if role == "ACCOUNTANT":
        return True
    return getattr(user, "has_feature_permission", lambda _: False)("accounting.view")


@login_required
def bursar_entries_report(request: HttpRequest):
    """Read-only report of fee/payment transactions for Accountant. RBAC: accounting.view or ACCOUNTANT."""
    if not _can_access_accounting(request.user):
        return HttpResponseForbidden("You do not have permission to view Bursar entries.")
    from apps.accounts.utils import get_dashboard_context
    payments = (
        Payment.objects.select_related("invoice__student", "invoice")
        .filter(status="completed")
        .order_by("-created_at")[:100]
    )
    dashboard_context = get_dashboard_context(request.user, "finance")
    return render(request, "finance/bursar_entries_report.html", {
        "payments": payments,
        "dashboard_context": dashboard_context,
    })


@login_required
def expense_vs_budget(request: HttpRequest):
    """Placeholder: Expense vs approved budget for Accountant. RBAC: accounting.view or ACCOUNTANT."""
    if not _can_access_accounting(request.user):
        return HttpResponseForbidden("You do not have permission to view expense vs budget.")
    from apps.accounts.utils import get_dashboard_context
    from .models import Budget, BudgetLine
    budgets = Budget.objects.select_related("academic_year").order_by("-academic_year__start_date")[:5]
    dashboard_context = get_dashboard_context(request.user, "finance")
    return render(request, "finance/expense_vs_budget.html", {
        "budgets": budgets,
        "dashboard_context": dashboard_context,
    })


@staff_member_required
def suspense_queue(request: HttpRequest):
    """
    Queue of unidentified deposits awaiting allocation.
    """
    queue = (
        SuspensePayment.objects.select_related(
            "bank_statement_entry",
            "bank_statement_entry__bank_account",
            "suggested_invoice",
            "suggested_student",
            "claimed_student",
        )
        .prefetch_related("allocations__invoice", "allocations__payment")
        .filter(status__in=[SuspensePayment.Status.OPEN, SuspensePayment.Status.PARTIAL])
        .order_by("-created_at")
    )
    return render(request, "finance/suspense_queue.html", {"queue": queue})


@staff_member_required
@require_POST
def claim_suspense_payment(request: HttpRequest, suspense_id: int):
    """
    Claim and allocate an unidentified payment.
    Expects JSON in `allocations`, e.g.:
      [{"invoice_id": 12, "amount": "10000"}, {"invoice_id": 13, "amount": "5000"}]
    """
    suspense = get_object_or_404(SuspensePayment, pk=suspense_id)
    raw_allocations = request.POST.get("allocations", "").strip()
    notes = request.POST.get("notes", "").strip()
    if not raw_allocations:
        messages.error(request, "Provide allocation JSON before submitting.")
        return redirect("finance:suspense_queue")

    try:
        allocations = json.loads(raw_allocations)
    except json.JSONDecodeError:
        messages.error(request, "Allocation payload must be valid JSON.")
        return redirect("finance:suspense_queue")

    try:
        result = BankStatementImportService().claim_suspense_payment(
            suspense_payment=suspense,
            allocations=allocations,
            claimed_by=request.user,
            notes=notes,
        )
    except FINANCE_SOFT_FAILURES as exc:
        messages.error(request, f"Failed to allocate suspense payment: {exc}")
        return redirect("finance:suspense_queue")

    messages.success(
        request,
        f"Suspense #{suspense.id} updated to {result['status']}. Remaining: {result['remaining']}.",
    )
    return redirect("finance:suspense_queue")


# Re-export reports views (2.1 decomposition)
from .views_reports import finance_reports, submit_report_request
