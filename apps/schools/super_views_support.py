"""
Global support ticket command center (BR-12 split from super_views).
"""

from __future__ import annotations

from django.shortcuts import redirect, render
from django.utils import timezone


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


def super_support_dashboard(request):
    """Global support ticket command center: list tickets with filters; HTMX refreshes queue."""
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket
    from apps.siteconfig.support_sla import (
        SUPPORT_SLA_RESPONSE_HOURS,
        SUPPORT_SLA_RESOLUTION_HOURS,
    )

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()
    qs = GlobalSupportTicket.objects.select_related(
        "school", "user", "assigned_to"
    ).order_by("-created_at")[:100]
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    tickets = list(qs)
    tickets = _annotate_tickets_sla(tickets)
    open_count = GlobalSupportTicket.objects.filter(
        status=GlobalSupportTicket.Status.OPEN
    ).count()
    in_progress_count = GlobalSupportTicket.objects.filter(
        status=GlobalSupportTicket.Status.IN_PROGRESS
    ).count()
    backlog_48h = sum(1 for t in tickets if t.age_hours >= 48)
    backlog_7d = sum(1 for t in tickets if t.age_hours >= (24 * 7))
    oldest_hours = max((t.age_hours for t in tickets), default=0.0)
    sla_breach_response = sum(
        1 for t in tickets if getattr(t, "sla_response_breach", False)
    )
    sla_breach_resolution = sum(
        1 for t in tickets if getattr(t, "sla_resolution_breach", False)
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
        },
    )


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
    ).order_by("-created_at")[:50]
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    tickets = _annotate_tickets_sla(list(qs))
    return render(
        request,
        "schools/super_support_queue_fragment.html",
        {
            "tickets": tickets,
            "request_user_id": getattr(request.user, "id", None),
            "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
            "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
        },
    )


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
    if request.headers.get("HX-Request"):
        status_filter = request.GET.get("status", "").strip()
        priority_filter = request.GET.get("priority", "").strip()
        qs = GlobalSupportTicket.objects.select_related(
            "school", "user", "assigned_to"
        ).order_by("-created_at")[:50]
        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        tickets = _annotate_tickets_sla(list(qs))
        return render(
            request,
            "schools/super_support_queue_fragment.html",
            {
                "tickets": tickets,
                "request_user_id": getattr(request.user, "id", None),
                "sla_response_hours": SUPPORT_SLA_RESPONSE_HOURS,
                "sla_resolution_hours": SUPPORT_SLA_RESOLUTION_HOURS,
            },
        )
    return redirect("super:support_dashboard")
