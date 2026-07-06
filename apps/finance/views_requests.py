"""
Finance notifications and requests inbox views (§6.15 app-by-app split — subdomain: requests).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from apps.accounts.decorators import require_permission
from django.db import models
from django.db.models import Count
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.urls import reverse

from services.post_delete_navigation import redirect_after_save

from .models import Notification, FinanceRequestAudit
from .views_common import _active_profile


def _requests_inbox_url(view_mode: str, severity_filter: str) -> str:
    return (
        f"{reverse('finance:requests')}?view={view_mode}"
        f"&severity={severity_filter.lower()}"
    )


@require_permission("finance.view", "finance.manage")
def notifications(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    # tenant-isolation-allow: scoped-to-recipient-or-creator-current-user
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
    return render(
        request,
        "finance/notifications.html",
        {
            "alerts": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query,
        },
    )


@require_permission("finance.view", "finance.manage")
def finance_requests(request: HttpRequest):
    # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
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
        base_qs.values("severity").order_by("severity").annotate(count=Count("id"))
    )
    severity_counts_dict = {row["severity"]: row["count"] for row in severity_counts}
    severity_options = [
        {
            "key": "ALL",
            "label": "All",
            "param": "all",
            "count": severity_counts_dict.get("ALL", 0),
        },
        {
            "key": "INFO",
            "label": "Info",
            "param": "info",
            "count": severity_counts_dict.get("INFO", 0),
        },
        {
            "key": "WARNING",
            "label": "Warning",
            "param": "warning",
            "count": severity_counts_dict.get("WARNING", 0),
        },
        {
            "key": "ALERT",
            "label": "Alert",
            "param": "alert",
            "count": severity_counts_dict.get("ALERT", 0),
        },
    ]

    if request.method == "POST":
        if request.POST.get("mark_all_unread"):
            targets = list(base_qs.filter(is_read=False))
            if targets:
                # tenant-isolation-allow: id-set-from-recipient-scoped-base-query
                Notification.objects.filter(id__in=[n.id for n in targets]).update(
                    is_read=True
                )
                for notif in targets:
                    FinanceRequestAudit.objects.create(
                        notification=notif,
                        user=request.user,
                        action="marked_read",
                        details="Marked all unread from finance inbox.",
                    )
                messages.success(
                    request, f"Marked {len(targets)} finance request(s) as read."
                )
            target = _requests_inbox_url(view_mode, severity_filter)
            return redirect_after_save(request, target, list_url=target)

        selected = request.POST.getlist("notification_id")
        if selected:
            targets = list(base_qs.filter(id__in=selected))
            if targets:
                # tenant-isolation-allow: id-set-from-recipient-scoped-base-query
                Notification.objects.filter(id__in=[n.id for n in targets]).update(
                    is_read=True
                )
                for notif in targets:
                    FinanceRequestAudit.objects.create(
                        notification=notif,
                        user=request.user,
                        action="marked_read",
                        details="Marked read from finance requests dashboard.",
                    )
                messages.success(
                    request, f"Marked {len(targets)} finance request(s) as read."
                )
        target = _requests_inbox_url(view_mode, severity_filter)
        return redirect_after_save(request, target, list_url=target)

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

    return render(
        request,
        "finance/requests.html",
        {
            "notifications": page_obj.object_list,
            "page_obj": page_obj,
            "unread_count": unread_count,
            "view_mode": view_mode,
            "severity_filter": severity_filter,
            "severity_counts": {
                row["severity"]: row["count"] for row in severity_counts
            },
            "severity_options": severity_options,
            "pagination_extra_query": pagination_extra_query,
            "finance_request_audits": list(
                FinanceRequestAudit.objects.select_related(
                    "notification", "user"
                ).order_by("-created_at")[:25]
            ),
            "page_title": "Finance access requests",
            "page_subtitle": "Review guardian requests and acknowledge them with a single action.",
            "action_url": reverse("finance:dashboard"),
        },
    )
