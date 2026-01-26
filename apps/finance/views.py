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
from django.views.decorators.http import require_http_methods, require_POST
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.utils.safestring import mark_safe

from django.template.loader import render_to_string

from apps.academics.models import AcademicYear
from apps.payroll.models import Payslip
from apps.siteconfig.models import SiteSettings, default_backend_feature_flags
from apps.siteconfig.dashboard_views import load_dashboard_layout_settings, _can_customize
from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata
from apps.evals.notifications import NotificationService

from .forms import ReportRequestForm
from .models import (
    ComplianceProfile,
    FeePlan,
    Invoice,
    LedgerAccount,
    Notification,
    FinanceRequestAudit,
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
from apps.communication.models import Message

logger = logging.getLogger(__name__)


def _active_profile() -> ComplianceProfile | None:
    site = SiteSettings.get_solo()
    if getattr(site, "compliance_profile", None):
        return site.compliance_profile
    return ComplianceProfile.objects.filter(is_active=True).first()


def _backend_flags() -> dict:
    """
    Convenience wrapper to merge default backend flags with saved settings.
    Safe for use in early request handling where DB might be missing values.
    """
    try:
        site = SiteSettings.get_solo()
        return {**default_backend_feature_flags(), **(site.backend_feature_flags or {})}
    except Exception:
        return default_backend_feature_flags()


def _finance_access_state(user) -> dict:
    """
    Snapshot of finance access for a guardian user.
    Returns counts, whether opt-in is required, and whether requests are allowed.
    """
    from apps.accounts.permissions import _guardian_finance_qs
    from apps.people.models import StudentGuardian

    flags = _backend_flags()
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
    dashboard_settings = load_dashboard_layout_settings(request.user, "finance")
    allow_custom_layout = _can_customize(request.user)
    dashboard_layout_url = reverse("api:dashboard-layout", kwargs={"page": "finance"})
    available_sidebar_items = [
        {"id": "finance-home", "label": "Finance Home", "url": reverse("finance:dashboard"), "icon": "bi-cash-stack"},
        {"id": "finance-invoices", "label": "Invoices", "url": reverse("finance:invoices"), "icon": "bi-receipt"},
        {"id": "finance-payments", "label": "Payments", "url": reverse("finance:payments"), "icon": "bi-wallet2"},
        {"id": "finance-trial", "label": "Trial Balance", "url": reverse("finance:trial_balance"), "icon": "bi-bank"},
        {"id": "finance-reports", "label": "Reports", "url": reverse("finance:reports"), "icon": "bi-graph-up-arrow"},
    ]
    widget_meta_json = mark_safe(json.dumps(get_dashboard_widget_metadata()))
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).order_by("-created_at")
    finance_request_link = f"{reverse('accounts:user_messages')}?subject=finance+access+request"

    context = {
        "profile": profile,
        "hero": hero,
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
    access_state = _finance_access_state(request.user)
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    status = request.GET.get("status")
    year_id = request.GET.get("year")
    qs = Invoice.objects.filter(profile=profile).select_related("student", "academic_year")
    
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
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian

    access_state = _finance_access_state(request.user)
    profile = _active_profile()
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    invoice = get_object_or_404(
        Invoice.objects.select_related("student", "academic_year", "counterparty"),
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
        invoice.attachment = request.FILES["attachment"]
        invoice.save(update_fields=["attachment"])
        messages.success(request, "Attachment uploaded.")
        return redirect("finance:invoice_detail", invoice_id=invoice.id)

    payment_link = generate_payment_link(invoice)
    reminder = getattr(invoice, "reminder", None)

    finance_summary = None
    if access_state["guardian_count"]:
        finance_summary = (
            f"{access_state['finance_count']} of {access_state['guardian_count']} linked student(s) "
            "currently have finance access."
        )

    return render(request, "finance/invoice_detail.html", {
        "invoice": invoice,
        "payment_link": payment_link,
        "reminder": reminder,
        "finance_access_required": access_state["require_opt_in"],
        "finance_access_granted": access_state["finance_count"] > 0,
        "finance_access_summary": finance_summary,
        "can_request_finance_access": access_state["allow_requests"] and access_state["require_opt_in"] and access_state["guardian_count"] > access_state["finance_count"],
        "finance_request_url": reverse("finance:invoice_request_access", args=[invoice.id]),
        "finance_guardian_count": access_state["finance_count"],
        "guardian_link_count": access_state["guardian_count"],
    })


@login_required
@require_POST
def request_finance_access(request: HttpRequest, invoice_id: int | None = None):
    """
    Allow guardians to request finance visibility from admins/finance.
    Sends internal messages and finance notifications to admin-aligned roles.
    """
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian, StudentProfile

    flags = _backend_flags()
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

        notifier = NotificationService()
        site = SiteSettings.get_solo()
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
                    except Exception:
                        logger.exception("Failed to send finance access SMS.")
            if "email" in channels and from_email and user.email:
                try:
                    send_mail(
                        subject="Finance access granted",
                        message=f"You can now view finance records for {student}.",
                        from_email=from_email,
                        recipient_list=[user.email],
                    )
                except Exception:
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
    site = SiteSettings.get_solo()
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
            except Exception:
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
                except Exception:
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

    flags = _backend_flags()
    site = SiteSettings.get_solo()
    channels = getattr(site, "notification_channels", []) or []
    from_email = getattr(site, "email_from_address", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    notifier = NotificationService()

    if request.method == "POST":
        with transaction.atomic():
            granted = pending_qs.update(can_view_finance=True)

        messages_out = []
        if granted:
            for link in pending_qs:
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
                        except Exception:
                            logger.exception("Failed to send finance access SMS.")
                if "email" in channels and from_email and user.email:
                    try:
                        send_mail(
                            subject="Finance access granted",
                            message=f"You can now view finance records for {link.student}.",
                            from_email=from_email,
                            recipient_list=[user.email],
                        )
                    except Exception:
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

    return render(request, "finance/requests.html", {
        "notifications": notifications_qs,
        "unread_count": unread_count,
        "view_mode": view_mode,
        "severity_filter": severity_filter,
        "severity_counts": {row["severity"]: row["count"] for row in severity_counts},
        "severity_options": severity_options,
        "finance_request_audits": list(
            FinanceRequestAudit.objects.select_related("notification", "user").order_by("-created_at")[:25]
        ),
    })
