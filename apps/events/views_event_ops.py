"""Analytics and DLQ remediation surfaces for the tenant event console."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from apps.events.models import (
    DomainEvent,
    EventSystemRemediationAudit,
    WebhookDelivery,
)
from apps.events.remediation_ops import (
    domain_dlq_queryset_for_school,
    ignore_domain_delivery,
    ignore_platform_delivery,
    platform_dlq_queryset_for_school,
    resolve_domain_delivery,
    resolve_platform_delivery,
    retry_domain_delivery,
    retry_platform_delivery,
)
from apps.events.views_console import _require_staff_school, _school_pk_str
from apps.platform_runtime.models import EventWebhookDelivery, PlatformEventLog

_MAX_BULK_REMEDIATION = 200


def _parse_newest_limit(raw: str | None) -> int:
    try:
        n = int(raw or 50)
    except ValueError:
        n = 50
    return max(1, min(n, 200))


def _duration_to_ms(duration) -> float | None:
    if duration is None:
        return None
    try:
        return round(duration.total_seconds() * 1000.0, 2)
    except AttributeError:
        return None


@never_cache
@login_required
@require_http_methods(["GET"])
def event_analytics_console(request):
    if not _require_staff_school(request):
        return HttpResponseForbidden("Staff on a school tenant host is required.")
    school = request.school
    sid = school.pk
    sid_str = str(sid)
    filter_event_type = (request.GET.get("event_type") or "").strip()
    newest_limit = _parse_newest_limit(request.GET.get("newest_limit"))

    domain_ev_qs = DomainEvent.objects.filter(school_id=sid)
    platform_ev_qs = PlatformEventLog.objects.filter(school_id=sid_str)
    if filter_event_type:
        domain_ev_qs = domain_ev_qs.filter(event_type=filter_event_type)
        platform_ev_qs = platform_ev_qs.filter(event_type=filter_event_type)

    domain_by_type = list(
        domain_ev_qs.values("event_type").annotate(c=Count("id")).order_by("-c")[:30]
    )
    domain_status_qs = DomainEvent.objects.filter(school_id=sid)
    if filter_event_type:
        domain_status_qs = domain_status_qs.filter(event_type=filter_event_type)
    domain_by_status = list(
        domain_status_qs.values("status").annotate(c=Count("id")).order_by("-c")
    )
    platform_by_type = list(
        platform_ev_qs.values("event_type").annotate(c=Count("id")).order_by("-c")[:30]
    )

    domain_failed_deliveries = WebhookDelivery.objects.filter(
        domain_event__school_id=sid,
        status=WebhookDelivery.Status.FAILED,
    ).count()
    domain_dlq_open = domain_dlq_queryset_for_school(
        sid, event_type=filter_event_type or None
    ).count()

    platform_failed_live = EventWebhookDelivery.objects.filter(
        subscription__school_id=sid_str,
        status=EventWebhookDelivery.Status.FAILED,
    ).count()
    platform_dlq_open = platform_dlq_queryset_for_school(
        sid_str, event_type=filter_event_type or None
    ).count()

    replay_attempts = PlatformEventLog.objects.filter(
        school_id=sid_str,
        event_type="platform_event_replayed",
    ).count()

    domain_latency = WebhookDelivery.objects.filter(
        domain_event__school_id=sid,
        status=WebhookDelivery.Status.DELIVERED,
        delivered_at__isnull=False,
    ).aggregate(
        avg_d=Avg(
            ExpressionWrapper(
                F("delivered_at") - F("created_at"),
                output_field=DurationField(),
            )
        )
    )["avg_d"]
    platform_latency = EventWebhookDelivery.objects.filter(
        subscription__school_id=sid_str,
        status=EventWebhookDelivery.Status.DELIVERED,
        delivered_at__isnull=False,
    ).aggregate(
        avg_d=Avg(
            ExpressionWrapper(
                F("delivered_at") - F("created_at"),
                output_field=DurationField(),
            )
        )
    )["avg_d"]

    recent_domain = list(
        DomainEvent.objects.filter(school_id=sid)
        .filter(Q(event_type=filter_event_type) if filter_event_type else Q())
        .order_by("-created_at")[:newest_limit]
    )
    recent_platform = list(
        PlatformEventLog.objects.filter(school_id=sid_str)
        .filter(Q(event_type=filter_event_type) if filter_event_type else Q())
        .order_by("-pk")[:newest_limit]
    )

    return render(
        request,
        "events/event_analytics.html",
        {
            "page_title": "Event analytics",
            "page_subtitle": (
                "Volume, failures, DLQ backlog, replay audits, and optional latency averages "
                f"(newest rows capped at {newest_limit})."
            ),
            "filter_event_type": filter_event_type,
            "newest_limit": newest_limit,
            "domain_by_type": domain_by_type,
            "domain_by_status": domain_by_status,
            "platform_by_type": platform_by_type,
            "domain_failed_deliveries": domain_failed_deliveries,
            "domain_dlq_open": domain_dlq_open,
            "platform_failed_live": platform_failed_live,
            "platform_dlq_open": platform_dlq_open,
            "replay_attempts": replay_attempts,
            "domain_latency_ms": _duration_to_ms(domain_latency),
            "platform_latency_ms": _duration_to_ms(platform_latency),
            "recent_domain": recent_domain,
            "recent_platform": recent_platform,
            "console_url": reverse("events:event_console"),
            "dlq_url": reverse("events:event_dlq_console"),
            "action_url": reverse("accounts:backend_dashboard"),
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def event_dlq_console(request):
    if not _require_staff_school(request):
        return HttpResponseForbidden("Staff on a school tenant host is required.")
    school = request.school
    sid = school.pk
    sid_str = _school_pk_str(request)
    filter_event_type = (request.GET.get("event_type") or "").strip()

    if request.method == "POST":
        return _event_dlq_remediate_post(request)

    domain_rows = list(
        domain_dlq_queryset_for_school(sid, event_type=filter_event_type or None)[
            :200
        ]
    )
    platform_rows = list(
        platform_dlq_queryset_for_school(sid_str, event_type=filter_event_type or None)[
            :200
        ]
    )
    audit_rows = list(
        EventSystemRemediationAudit.objects.filter(school_id=sid).order_by(
            "-created_at"
        )[:50]
    )

    return render(
        request,
        "events/event_dlq.html",
        {
            "page_title": "Dead-letter queue",
            "page_subtitle": (
                "Failed webhook deliveries past retry thresholds. Retry schedules a new attempt; "
                "resolve or ignore keeps the row closed with an audit trail."
            ),
            "filter_event_type": filter_event_type,
            "domain_rows": domain_rows,
            "platform_rows": platform_rows,
            "audit_rows": audit_rows,
            "console_url": reverse("events:event_console"),
            "analytics_url": reverse("events:event_analytics_console"),
            "remediate_url": reverse("events:event_dlq_console"),
            "action_url": reverse("accounts:backend_dashboard"),
        },
    )


@require_POST
def _event_dlq_remediate_post(request):
    if not _require_staff_school(request):
        return HttpResponseForbidden("Staff on a school tenant host is required.")
    school = request.school
    sid = school.pk
    sid_str = _school_pk_str(request)
    action = (request.POST.get("action") or "").strip()
    reason = (request.POST.get("reason") or "").strip()
    filter_event_type = (request.POST.get("filter_event_type") or "").strip()

    domain_sel = [int(x) for x in request.POST.getlist("domain_delivery_ids") if x.isdigit()]
    plat_sel = [int(x) for x in request.POST.getlist("platform_delivery_ids") if x.isdigit()]

    domain_base = domain_dlq_queryset_for_school(sid, event_type=filter_event_type or None)
    plat_base = platform_dlq_queryset_for_school(
        sid_str, event_type=filter_event_type or None
    )

    def _cap(xs):
        return xs[:_MAX_BULK_REMEDIATION]

    if action in ("resolve_selected", "ignore_selected") and not reason:
        messages.error(request, "Reason is required for resolve / ignore.")
        redir = reverse("events:event_dlq_console")
        q = []
        if filter_event_type:
            q.append(f"event_type={filter_event_type}")
        qs = ("?" + "&".join(q)) if q else ""
        return redirect(f"{redir}{qs}")

    try:
        with transaction.atomic():
            if action == "retry_selected":
                for pk in _cap(domain_sel):
                    d = domain_base.filter(pk=pk).select_for_update().first()
                    if d:
                        retry_domain_delivery(d, request.user)
                for pk in _cap(plat_sel):
                    d = plat_base.filter(pk=pk).select_for_update().first()
                    if d:
                        retry_platform_delivery(d, request.user)
                messages.success(request, "Retry queued for selected deliveries.")
            elif action == "retry_all_filtered":
                domain_ids = list(
                    domain_base.values_list("pk", flat=True)[:_MAX_BULK_REMEDIATION]
                )
                plat_ids = list(
                    plat_base.values_list("pk", flat=True)[:_MAX_BULK_REMEDIATION]
                )
                for pk in domain_ids:
                    d = (
                        WebhookDelivery.objects.select_for_update()
                        .filter(pk=pk)
                        .first()
                    )
                    if d:
                        retry_domain_delivery(d, request.user)
                for pk in plat_ids:
                    d = (
                        EventWebhookDelivery.objects.select_for_update()
                        .filter(pk=pk)
                        .first()
                    )
                    if d:
                        retry_platform_delivery(d, request.user)
                messages.success(
                    request,
                    "Retry queued for all filtered DLQ rows (bulk cap applies).",
                )
            elif action in ("resolve_selected", "ignore_selected"):
                for pk in _cap(domain_sel):
                    d = domain_base.filter(pk=pk).select_for_update().first()
                    if d:
                        if action == "resolve_selected":
                            resolve_domain_delivery(d, request.user, reason=reason)
                        else:
                            ignore_domain_delivery(d, request.user, reason=reason)
                for pk in _cap(plat_sel):
                    d = plat_base.filter(pk=pk).select_for_update().first()
                    if d:
                        if action == "resolve_selected":
                            resolve_platform_delivery(d, request.user, reason=reason)
                        else:
                            ignore_platform_delivery(d, request.user, reason=reason)
                messages.success(request, "Disposition recorded with audit entries.")
            else:
                messages.error(request, "Unknown remediation action.")
    except Exception as exc:
        messages.error(request, f"Remediation failed: {exc}")

    redir = reverse("events:event_dlq_console")
    q = []
    if filter_event_type:
        q.append(f"event_type={filter_event_type}")
    qs = ("?" + "&".join(q)) if q else ""
    return redirect(f"{redir}{qs}")
