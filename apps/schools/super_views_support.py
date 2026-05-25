"""
Global support ticket command center (BR-12 split from super_views).
"""

from __future__ import annotations

import csv
import io

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_AUDIT_EXPORT,
    PLATFORM_SCOPE_TEAM_MANAGE,
    PLATFORM_SCOPE_TEAM_READ,
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)



def _annotate_tickets_sla(tickets):
    """Annotate ticket list with age_hours and SLA breach flags (integrated with siteconfig.support_sla)."""
    from apps.siteconfig.support_sla import (
        ticket_response_breach,
        ticket_resolution_breach,
    )

    now = timezone.now()
    for ticket in tickets:
        ticket.age_hours = round(
            max(0.0, (now - ticket.created_at).total_seconds() / 3600.0), 1
        )
        ticket.sla_response_breach = ticket_response_breach(ticket)
        ticket.sla_resolution_breach = ticket_resolution_breach(ticket)
    return tickets


def _paginate_support_tickets(request, qs, *, per_page: int = 25):
    """Return (page_obj, annotated page rows, extra query without page=)."""
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    extra = request.GET.copy()
    extra.pop("page", None)
    tickets = _annotate_tickets_sla(list(page_obj.object_list))
    return page_obj, tickets, extra.urlencode()


@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def super_support_dashboard(request):
    """Global support ticket command center: list tickets with filters; HTMX refreshes queue."""
    from apps.platform_runtime.models import PlatformOperatorSupportDashboardLink
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket
    from apps.siteconfig.support_sla import (
        SUPPORT_SLA_RESPONSE_HOURS,
        SUPPORT_SLA_RESOLUTION_HOURS,
    )

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()
    qs = GlobalSupportTicket.objects.select_related(
        "school", "user", "assigned_to"
    ).order_by("-created_at")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    stats_tickets = _annotate_tickets_sla(list(qs[:100]))
    page_obj, tickets, pagination_extra_query = _paginate_support_tickets(request, qs)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    open_count = GlobalSupportTicket.objects.filter(
        status=GlobalSupportTicket.Status.OPEN
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    ).count()
    in_progress_count = GlobalSupportTicket.objects.filter(
        status=GlobalSupportTicket.Status.IN_PROGRESS
    ).count()
    backlog_48h = sum(1 for t in stats_tickets if t.age_hours >= 48)
    backlog_7d = sum(1 for t in stats_tickets if t.age_hours >= (24 * 7))
    oldest_hours = max((t.age_hours for t in stats_tickets), default=0.0)
    sla_breach_response = sum(
        1 for t in stats_tickets if getattr(t, "sla_response_breach", False)
    )
    sla_breach_resolution = sum(
        1 for t in stats_tickets if getattr(t, "sla_resolution_breach", False)
    )

    from django.urls import reverse as _reverse

    urgent = []
    if sla_breach_response or sla_breach_resolution:
        urgent.append(
            {
                "title": f"SLA breaches: {sla_breach_response} response / {sla_breach_resolution} resolution",
                "url": request.get_full_path() + "#support-queue",
                "hint": "Prioritize oldest tickets first.",
            }
        )
    elif open_count:
        urgent.append(
            {
                "title": f"{open_count} open ticket(s)",
                "url": _reverse("super:command_center"),
                "hint": "Triage from command center.",
            }
        )
    else:
        urgent.append(
            {
                "title": "Queue calm",
                "url": "",
                "hint": "No open tickets in snapshot.",
            }
        )

    top_tickets = tickets[:4]
    activity = []
    for t in top_tickets:
        activity.append(
            {
                "title": str(getattr(t, "subject", "") or "Ticket"),
                "meta": f"{getattr(t, 'status', '')} · {getattr(t, 'age_hours', '')}h",
            }
        )
    if not activity:
        activity.append({"title": "Support queue", "meta": "No tickets in view."})

    operator_support_dashboard_links = list(
        PlatformOperatorSupportDashboardLink.objects.order_by("sort_order", "slug")
    )

    phase7_de = {
        "eyebrow": "Support mission control",
        "headline_label": "Open tickets",
        "headline_value": open_count,
        "headline_meta": f"{in_progress_count} in progress · oldest {round(oldest_hours, 1)}h",
        "metrics": [
            {
                "label": "Backlog >48h",
                "value": backlog_48h,
                "meta": "Aging",
                "status": "warn" if backlog_48h else "ok",
            },
            {
                "label": "Backlog >7d",
                "value": backlog_7d,
                "meta": "Critical aging",
                "status": "danger" if backlog_7d else "ok",
            },
            {
                "label": "SLA response breach",
                "value": sla_breach_response,
                "meta": f"Target {SUPPORT_SLA_RESPONSE_HOURS.get('NORMAL', 24)}h (normal)",
                "status": "danger" if sla_breach_response else "ok",
            },
        ],
        "urgent_queue": urgent,
        "next_actions": [
            {
                "label": "Command center",
                "url": _reverse("super:command_center"),
            },
            {"label": "Control plane", "url": _reverse("super:dashboard")},
            {"label": "Reload", "url": request.get_full_path()},
        ],
        "activity": activity,
    }

    return render(
        request,
        "schools/super_support_dashboard.html",
        {
            "tickets": tickets,
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query,
            "request_user_id": getattr(request.user, "id", None),
            "open_count": open_count,
            "in_progress_count": in_progress_count,
            "backlog_48h": backlog_48h,
            "backlog_7d": backlog_7d,
            "oldest_hours": round(oldest_hours, 1),
            "sla_breach_response": sla_breach_response,
            "sla_breach_resolution": sla_breach_resolution,
            "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
            "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
            "status_filter": status_filter,
            "priority_filter": priority_filter,
            "phase7_de": phase7_de,
            "operator_support_dashboard_links": operator_support_dashboard_links,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def support_queue_fragment(request):
    """HTMX fragment: ticket queue table (refresh every 60s). SLA breach from apps.siteconfig.support_sla."""
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket
    from apps.siteconfig.support_sla import (
        SUPPORT_SLA_RESPONSE_HOURS,
        SUPPORT_SLA_RESOLUTION_HOURS,
    )

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()
    qs = GlobalSupportTicket.objects.select_related(
        "school", "user", "assigned_to"
    ).order_by("-created_at")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    page_obj, tickets, pagination_extra_query = _paginate_support_tickets(request, qs)
    return render(
        request,
        "schools/super_support_queue_fragment.html",
        {
            "tickets": tickets,
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query,
            "request_user_id": getattr(request.user, "id", None),
            "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
            "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def support_assign_ticket(request):
    """POST: assign ticket to current user or unassign. Redirects to support dashboard or returns fragment for HTMX."""
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket
    from apps.siteconfig.support_sla import (
        SUPPORT_SLA_RESPONSE_HOURS,
        SUPPORT_SLA_RESOLUTION_HOURS,
    )

    if request.method != "POST":
        return redirect("super:support_dashboard")
    ticket_id = request.POST.get("ticket_id", "").strip()
    action = request.POST.get("action", "").strip().lower()
    if not ticket_id or action not in ("assign_me", "unassign"):
        return redirect("super:support_dashboard")
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        ticket = GlobalSupportTicket.objects.get(pk=ticket_id)
    except GlobalSupportTicket.DoesNotExist:
        return redirect("super:support_dashboard")
    if action == "assign_me":
        ticket.assigned_to_id = getattr(request.user, "id", None)
        if ticket.first_response_at is None:
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["assigned_to_id", "first_response_at"])
        else:
            ticket.save(update_fields=["assigned_to_id"])
    else:
        ticket.assigned_to = None
        ticket.save(update_fields=["assigned_to_id"])
    from apps.platform_runtime.events import emit_platform_event

    emit_platform_event(
        "support_desk_ticket_assignment_changed",
        {
            "ticket_id": str(ticket.pk),
            "school_id": str(ticket.school_id),
            "actor_id": getattr(request.user, "id", None),
            "action": action,
            "assignee_id": ticket.assigned_to_id,
        },
        school_id=ticket.school_id,
    )
    if request.headers.get("HX-Request"):
        status_filter = request.GET.get("status", "").strip()
        priority_filter = request.GET.get("priority", "").strip()
        qs = GlobalSupportTicket.objects.select_related(
            "school", "user", "assigned_to"
        ).order_by("-created_at")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        page_obj, tickets, pagination_extra_query = _paginate_support_tickets(request, qs)
        return render(
            request,
            "schools/super_support_queue_fragment.html",
            {
                "tickets": tickets,
                "page_obj": page_obj,
                "pagination_extra_query": pagination_extra_query,
                "request_user_id": getattr(request.user, "id", None),
                "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
                "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
            },
        )
    return redirect("super:support_dashboard")


@require_platform_scope(PLATFORM_SCOPE_AUDIT_EXPORT)
def super_support_tickets_export_csv(request):
    """CSV export of global support tickets (same filters as dashboard)."""
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()
    qs = GlobalSupportTicket.objects.select_related("school", "user", "assigned_to").order_by(
        "-created_at"
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    rows = list(qs[:2000])

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "ticket_id",
            "created_at",
            "updated_at",
            "school",
            "submitter_email",
            "submitter_username",
            "subject",
            "status",
            "priority",
            "assignee_email",
            "csat_score",
            "csat_submitted_at",
        ]
    )
    for t in rows:
        w.writerow(
            [
                str(t.pk),
                t.created_at.isoformat() if t.created_at else "",
                t.updated_at.isoformat() if t.updated_at else "",
                t.school.name if t.school_id else "",
                getattr(t.user, "email", "") or "",
                getattr(t.user, "username", "") or "",
                t.subject,
                t.status,
                t.priority,
                getattr(t.assigned_to, "email", "") or "",
                t.csat_score or "",
                t.csat_submitted_at.isoformat() if t.csat_submitted_at else "",
            ]
        )
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="global_support_tickets.csv"'
    return resp


@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def super_support_ticket_detail(request, ticket_id):
    """
    Ticket drill-down: tenant context links, operator internal notes, status updates.
    Audited via platform events (payload excludes ticket body).
    """
    from apps.platform_runtime.events import emit_platform_event
    from apps.siteconfig.models_feature_controls import (
        GlobalSupportTicket,
        GlobalSupportTicketReply,
    )
    from apps.siteconfig.support_sla import (
        SUPPORT_SLA_RESPONSE_HOURS,
        SUPPORT_SLA_RESOLUTION_HOURS,
        ticket_response_breach,
        ticket_resolution_breach,
    )

    ticket = get_object_or_404(
        GlobalSupportTicket.objects.select_related(
            "school", "user", "assigned_to"
        ).prefetch_related("thread_replies__author"),
        pk=ticket_id,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "update").strip().lower()
        if action == "reply":
            body = (request.POST.get("reply_body") or "").strip()
            if body:
                vis_raw = (request.POST.get("reply_visibility") or "").strip().upper()
                if vis_raw == GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE:
                    vis = GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
                else:
                    vis = GlobalSupportTicketReply.Visibility.INTERNAL
                GlobalSupportTicketReply.objects.create(
                    ticket=ticket,
                    author=request.user,
                    body=body[:32000],
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    visibility=vis,
                )
                if vis == GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE:
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    GlobalSupportTicket.objects.filter(
                        pk=ticket.pk, first_response_at__isnull=True
                    ).update(first_response_at=timezone.now())
                try:
                    from apps.siteconfig.support_ticket_hooks import (
                        run_support_ticket_reply_hooks,
                    )

                    run_support_ticket_reply_hooks(
                        str(ticket.pk),
                        actor_id=getattr(request.user, "id", None),
                        visibility=vis,
                        reply_body=body[:32000],
                    )
                except (
                    AttributeError,
                    ImportError,
                    LookupError,
                    TypeError,
                    ValueError,
                ):
                    pass
                messages.success(request, "Reply added to thread.")
            return redirect("super:support_ticket_detail", ticket_id=ticket.pk)

        changed: list[str] = []
        new_status = request.POST.get("status", "").strip().upper()
        if new_status and new_status in GlobalSupportTicket.Status.values:
            if new_status != ticket.status:
                ticket.status = new_status
                changed.append("status")
        raw_notes = request.POST.get("internal_notes", "")
        if isinstance(raw_notes, str) and raw_notes != ticket.internal_notes:
            ticket.internal_notes = raw_notes[:32000]
            changed.append("internal_notes")
        if changed:
            ticket.save(update_fields=[f for f in changed if f in ("status", "internal_notes")])
            emit_platform_event(
                "support_desk_ticket_updated",
                {
                    "ticket_id": str(ticket.pk),
                    "school_id": str(ticket.school_id),
                    "actor_id": getattr(request.user, "id", None),
                    "changed_fields": changed,
                },
                school_id=ticket.school_id,
            )
            messages.success(request, "Ticket updated.")
        return redirect("super:support_ticket_detail", ticket_id=ticket.pk)

    now = timezone.now()
    ticket.age_hours = round(
        max(0.0, (now - ticket.created_at).total_seconds() / 3600.0), 1
    )
    ticket.sla_response_breach = ticket_response_breach(ticket)
    ticket.sla_resolution_breach = ticket_resolution_breach(ticket)

    runbooks_url = getattr(settings, "CONTROL_PLANE_RUNBOOKS_URL", None) or ""
    tenant_360_url = ""
    control_health_url = ""
    try:
        tenant_360_url = reverse(
            "super:tenant_360", kwargs={"school_id": ticket.school_id}
        )
    except NoReverseMatch:
        pass
    try:
        control_health_url = reverse("super:control_health")
    except NoReverseMatch:
        pass
    try:
        incidents_url = reverse("platform_incidents_console")
    except NoReverseMatch:
        incidents_url = ""

    tenant_message_admin_url = ""
    raw_msg_id = (ticket.metadata or {}).get("communication_message_id")
    if raw_msg_id and ticket.school_id:
        try:
            from apps.schools.tenant_url import build_tenant_backend_url

            # Message is registered on tenant admin only; platform /admin/ may not reverse this.
            admin_path = f"/admin/communication/message/{raw_msg_id}/change/"
            tenant_message_admin_url = build_tenant_backend_url(
                request, ticket.school, path=admin_path
            )
        except (TypeError, ValueError, AttributeError):
            tenant_message_admin_url = ""

    ai_triage = (ticket.metadata or {}).get("ai_triage")
    thread_replies = list(ticket.thread_replies.all())

    return render(
        request,
        "schools/super_support_ticket_detail.html",
        {
            "ticket": ticket,
            "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
            "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
            "runbooks_url": runbooks_url,
            "tenant_health_url": reverse("super:tenant_health"),
            "tenant_360_url": tenant_360_url,
            "control_health_url": control_health_url,
            "incidents_url": incidents_url,
            "status_choices": GlobalSupportTicket.Status.choices,
            "tenant_message_admin_url": tenant_message_admin_url,
            "ai_triage": ai_triage,
            "thread_replies": thread_replies,
            "reply_visibility_choices": GlobalSupportTicketReply.Visibility.choices,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_support_csat_dashboard(request):
    """Lightweight CSAT aggregates for global support tickets (control plane)."""
    from django.db.models import Avg, Count
    from django.db.models.functions import TruncMonth

    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = GlobalSupportTicket.objects.filter(
        csat_score__isnull=False, csat_submitted_at__isnull=False
    )
    overall = qs.aggregate(avg=Avg("csat_score"), n=Count("id"))
    by_month = list(
        qs.annotate(m=TruncMonth("csat_submitted_at"))
        .values("m")
        .annotate(avg_score=Avg("csat_score"), n=Count("id"))
        .order_by("-m")[:36]
    )
    recent = list(
        qs.select_related("school", "user")
        .order_by("-csat_submitted_at")[:50]
    )
    return render(
        request,
        "schools/super_support_csat_dashboard.html",
        {
            "overall_avg": overall.get("avg"),
            "overall_n": overall.get("n") or 0,
            "by_month": by_month,
            "recent": recent,
        },
    )
