"""
Workforce & money command center (HR + payroll + finance ops) — batch 1511.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse

from apps.finance.models import Notification, OfflinePaymentIntent
from apps.finance.models_offline_capture import FinanceOfflineCaptureRecord
from apps.payroll.models import LeaveRequest, PayrollRun
from apps.payroll.models_offline_capture import PayrollOfflineCaptureRecord
from apps.people.models import TeacherLeaveRequest

from .views_common import _active_profile


@staff_member_required(login_url=settings.LOGIN_URL)
def workforce_command_center(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    school = getattr(request, "school", None)
    school_id = school.pk if school is not None else None

    if school_id:
        finance_pending = FinanceOfflineCaptureRecord.objects.filter(
            school_id=school_id,
            status=FinanceOfflineCaptureRecord.Status.PENDING_REVIEW,
        )
        payroll_pending = PayrollOfflineCaptureRecord.objects.filter(
            school_id=school_id,
            status=PayrollOfflineCaptureRecord.Status.PENDING_REVIEW,
        )
    else:
        finance_pending = FinanceOfflineCaptureRecord.objects.none()
        payroll_pending = PayrollOfflineCaptureRecord.objects.none()

    offline_intents = OfflinePaymentIntent.objects.filter(
        status=OfflinePaymentIntent.Status.QUEUED_REVIEW,
        invoice__profile=profile,
    )
    if school_id:
        offline_intents = offline_intents.filter(invoice__school_id=school_id)

    latest_run = (
        PayrollRun.objects.filter(profile=profile).order_by("-period_start").first()
    )
    leave_pending = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING)
    teacher_leave_pending = TeacherLeaveRequest.objects.filter(
        status=TeacherLeaveRequest.Status.PENDING
    )
    if school_id:
        teacher_leave_pending = teacher_leave_pending.filter(teacher__school_id=school_id)

    # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
    finance_access_alerts = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
        is_read=False,
    ).count()

    return render(
        request,
        "finance/workforce_command_center.html",
        {
            "profile": profile,
            "finance_pending_count": finance_pending.count(),
            "payroll_pending_count": payroll_pending.count(),
            "offline_intent_count": offline_intents.count(),
            "finance_access_alerts": finance_access_alerts,
            "latest_payroll_run": latest_run,
            "leave_pending_count": leave_pending.count(),
            "teacher_leave_pending_count": teacher_leave_pending.count(),
            "links": {
                "finance_dashboard": reverse("finance:dashboard"),
                "payroll_dashboard": reverse("payroll:dashboard"),
                "offline_queue": reverse("finance:offline_payment_intent_queue"),
                "payment_command": reverse("finance:global_payment_command_center"),
                "identity_roster": reverse("accounts:tenant_identity_roster"),
            },
            "page_title": "Workforce & money",
            "page_subtitle": "HR, payroll, bursar, and global payment corridors in one operator surface.",
        },
    )
