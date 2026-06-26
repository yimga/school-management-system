"""
Finance access request views (§6.15 app-by-app split — subdomain: access).

Guardian finance access requests and staff bulk-grant. Single place for
finance visibility request flows and notifications.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.http import require_POST
from apps.schoolops.email_compat import send_mail

from apps.evals.notifications import NotificationService
from apps.communication.models import Message
from apps.siteconfig.config_service import get_effective_site_settings

from .models import Invoice, Notification
from .views_common import (
    FINANCE_SOFT_FAILURES,
    _backend_flags,
    _create_finance_request_notification,
    _notification_delivery_settings,
    finance_save_redirect,
)

logger = logging.getLogger(__name__)


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
        return HttpResponseForbidden(
            "Finance access requests are disabled by the administrator."
        )

    role = getattr(request.user, "role", "")
    is_staff_like = request.user.is_staff or request.user.is_superuser
    if role != User.Role.PARENT and not is_staff_like:
        return HttpResponseForbidden(
            "Only guardians or staff can manage finance access."
        )

    if is_staff_like and request.method == "POST" and request.POST.get("student_id"):
        try:
            student_id = int(request.POST.get("student_id"))
        except (TypeError, ValueError):
            messages.error(request, "Invalid student selection.")
            return finance_save_redirect(request, "finance:invoices")

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        student = StudentProfile.objects.filter(id=student_id).first()
        if not student:
            messages.error(request, "Student not found.")
            return finance_save_redirect(request, "finance:invoices")

        guardians = StudentGuardian.objects.filter(student=student).select_related(
            "guardian_user"
        )
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
        channels, from_email = _notification_delivery_settings(request, site=site)

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
            messages_out.append(
                Message(
                    sender=request.user,
                    recipient=user,
                    subject="Finance access granted",
                    body=f"You can now view finance records for {student}.",
                )
            )
            if "sms" in channels:
                phone = (
                    getattr(user, "phone", None)
                    or getattr(user, "phone_number", None)
                    or getattr(getattr(user, "profile", None), "phone", None)
                )
                if phone:
                    try:
                        notifier.send_sms(
                            phone, f"Finance access granted for {student}."
                        )
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
        return finance_save_redirect(request, "finance:invoices")

    guardian_links = StudentGuardian.objects.filter(
        guardian_user=request.user
    ).select_related("student")
    if request.method == "POST" and request.POST.get("student_id"):
        try:
            student_id = int(request.POST.get("student_id"))
        except (TypeError, ValueError):
            student_id = None
        if student_id and guardian_links.filter(student_id=student_id).exists():
            guardian_links = guardian_links.filter(student_id=student_id)
    if not guardian_links.exists():
        messages.error(request, "Link a student first to route your request.")
        return finance_save_redirect(request, "finance:invoices")

    invoice_ref = None
    if invoice_id:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        invoice = (
            Invoice.objects.filter(id=invoice_id).select_related("student").first()
        )
        if not invoice:
            return HttpResponseForbidden("Invoice not found.")
        if (
            invoice.student_id
            and not guardian_links.filter(student_id=invoice.student_id).exists()
        ):
            return HttpResponseForbidden(
                "You can only request access for your linked students."
            )
        invoice_ref = invoice.reference or str(invoice.id)

    recipients = User.objects.filter(
        models.Q(
            role__in=[
                User.Role.ADMIN,
                User.Role.BURSAR,
                User.Role.LEADERSHIP,
                User.Role.IT_ADMIN,
                User.Role.SUPERADMIN,
            ]
        )
        | models.Q(is_superuser=True)
    ).distinct()

    if not recipients.exists():
        messages.warning(
            request,
            "No admin recipients were found to notify. Please contact the school directly.",
        )
        return finance_save_redirect(request, "finance:invoices")

    student_names = ", ".join(str(link.student) for link in guardian_links)
    subject = "Finance access request"
    body_lines = [
        f"Guardian {request.user.get_full_name() or request.user.username} ({request.user.email}) requested finance access.",
        f"Linked students: {student_names or 'None'}",
    ]
    if invoice_ref:
        body_lines.append(f"Reference invoice: {invoice_ref}")
    body_lines.append(
        f"Finance opt-in required: {'Yes' if flags.get('require_guardian_finance_opt_in') else 'No'}"
    )
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
        Message(
            sender=request.user,
            recipient=recipient,
            subject=subject,
            body=body,
        )
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

    site = get_effective_site_settings(request=request)
    channels, from_email = _notification_delivery_settings(request, site=site)
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
                    notifier.send_sms(
                        phone,
                        f"Finance access request from {request.user.get_full_name() or request.user.username}.",
                    )
                except FINANCE_SOFT_FAILURES:
                    logger.exception("Failed to send finance access SMS notification.")

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
        from apps.communication.comms_locale import locale_target_for_user

        Message.objects.create(
            sender=request.user,
            recipient=request.user,
            subject="Finance access confirmation",
            body="Finance access is already enabled for your linked students. You can view invoices now.",
            locale_target=locale_target_for_user(request.user),
        )

    messages.success(request, "Request sent to the admin/finance team.")
    return finance_save_redirect(request, "finance:invoices")


@staff_member_required(login_url=settings.LOGIN_URL)
def finance_access_bulk(request: HttpRequest):
    """
    Staff page to bulk-grant guardian finance access by year/class with
    audit-friendly notifications.
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
    channels, from_email = _notification_delivery_settings(request, site=site)
    notifier = NotificationService()

    if request.method == "POST":
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
                messages_out.append(
                    Message(
                        sender=request.user,
                        recipient=user,
                        subject="Finance access granted",
                        body=f"You can now view finance records for {link.student}.",
                    )
                )
                if "sms" in channels:
                    phone = (
                        getattr(user, "phone", None)
                        or getattr(user, "phone_number", None)
                        or getattr(getattr(user, "profile", None), "phone", None)
                    )
                    if phone:
                        try:
                            notifier.send_sms(
                                phone,
                                f"Finance access granted for {link.student}.",
                            )
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
        messages.success(
            request,
            f"Granted finance access to {granted} guardian link(s).",
        )
        from services.post_delete_navigation import redirect_after_save

        target = request.path + f"?year={selected_year}&classroom={selected_class}"
        return redirect_after_save(request, target, list_url=target)

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
