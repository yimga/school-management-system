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
            "support_bulk_actions": [
                {"slug": "assign_me", "label": "Assign to me", "variant": "default"},
                {"slug": "in_progress", "label": "Mark in progress", "variant": "default"},
                {"slug": "waiting", "label": "Waiting on submitter", "variant": "default"},
                {"slug": "resolve", "label": "Resolve", "variant": "default"},
                {"slug": "escalate", "label": "Escalate priority", "variant": "danger"},
            ],
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
                    body=body[:32000],  # magic-number-allow: text-body-char-truncation-cap
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
                        reply_body=body[:32000],  # magic-number-allow: text-body-char-truncation-cap
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

        # v4.00.45 — AI triage feedback (accept / override).
        if action in ("ai_triage_accept", "ai_triage_override"):
            metadata = dict(ticket.metadata or {})
            triage = dict(metadata.get("ai_triage") or {})
            feedback = list(metadata.get("ai_triage_feedback") or [])
            applied_priority = (request.POST.get("applied_priority") or "").strip().upper()
            applied_category = (request.POST.get("applied_category") or "").strip().lower()
            decision = "accepted" if action == "ai_triage_accept" else "overridden"
            from apps.siteconfig.models_feature_controls import GlobalSupportTicket

            valid_priorities = {p for p, _ in GlobalSupportTicket.Priority.choices}
            updated_fields: list[str] = []
            if applied_priority in valid_priorities and applied_priority != ticket.priority:
                ticket.priority = applied_priority
                updated_fields.append("priority")
            if applied_category:
                metadata["category"] = applied_category[:64]
            feedback.append(
                {
                    "actor_id": getattr(request.user, "id", None),
                    "decision": decision,
                    "applied_priority": applied_priority,
                    "applied_category": applied_category,
                    "ai_priority": (triage.get("priority_suggestion") or "").upper(),
                    "ai_category": (triage.get("category") or "").lower(),
                    "at": timezone.now().isoformat(),
                }
            )
            metadata["ai_triage_feedback"] = feedback[-20:]
            ticket.metadata = metadata
            updated_fields.append("metadata")
            ticket.save(update_fields=list(set(updated_fields)) + ["updated_at"])
            try:
                from services.ai_helpers import record_feedback

                record_feedback(
                    school=getattr(ticket, "school", None),
                    task_type_name="NARRATIVE",
                    tier="support_ai_triage",
                    accepted=(decision == "accepted"),
                )
            except (AttributeError, ImportError, LookupError, TypeError, ValueError):
                pass
            messages.success(
                request,
                "AI triage " + decision + ".",
            )
            return redirect("super:support_ticket_detail", ticket_id=ticket.pk)

        # v4.00.49 — AI drafted reply: generate / accept (auto-post) / discard.
        if action == "ai_draft_generate":
            try:
                from apps.siteconfig.support_ai_reply import run_ai_draft_reply

                tone = (request.POST.get("draft_tone") or "warm").strip().lower()
                draft = run_ai_draft_reply(ticket, request=request, tone=tone)
            except (AttributeError, ImportError, LookupError, TypeError, ValueError):
                draft = None
            if draft is None:
                messages.warning(request, "AI draft is unavailable right now. Try again or reply manually.")
            else:
                messages.success(
                    request,
                    f"AI draft ready ({draft.get('confidence', '')} confidence).",
                )
            return redirect("super:support_ticket_detail", ticket_id=ticket.pk)

        if action in ("ai_draft_accept", "ai_draft_discard"):
            metadata = dict(ticket.metadata or {})
            draft = dict(metadata.get("ai_draft_reply") or {})
            edited_text = (request.POST.get("draft_text") or "").strip()
            original_text = (draft.get("draft_text") or "").strip()
            decision = "discarded"
            edited = False
            if action == "ai_draft_accept" and edited_text:
                if edited_text != original_text:
                    decision = "edited"
                    edited = True
                else:
                    decision = "accepted"
                GlobalSupportTicketReply.objects.create(
                    ticket=ticket,
                    author=request.user,
                    body=edited_text[:32000],  # magic-number-allow: text-body-char-truncation-cap
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    visibility=GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE,
                )
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                GlobalSupportTicket.objects.filter(
                    pk=ticket.pk, first_response_at__isnull=True
                ).update(first_response_at=timezone.now())
                # Clear the persisted draft once it's been used.
                metadata.pop("ai_draft_reply", None)
                ticket.metadata = metadata
                ticket.save(update_fields=["metadata", "updated_at"])
                messages.success(
                    request,
                    "AI draft posted as reply." + (" (edited)" if edited else ""),
                )
            elif action == "ai_draft_discard":
                metadata.pop("ai_draft_reply", None)
                ticket.metadata = metadata
                ticket.save(update_fields=["metadata", "updated_at"])
                messages.success(request, "AI draft discarded.")
            try:
                from apps.siteconfig.support_ai_reply import record_draft_feedback

                record_draft_feedback(
                    ticket,
                    decision=decision,
                    edited=edited,
                    applied_text=edited_text if action == "ai_draft_accept" else "",
                )
            except (AttributeError, ImportError, LookupError, TypeError, ValueError):
                pass
            return redirect("super:support_ticket_detail", ticket_id=ticket.pk)

        # v4.00.43 — promote ticket to public incident.
        if action == "promote_incident":
            from apps.siteconfig.models_feature_controls import PublicIncident

            title = (request.POST.get("incident_title") or ticket.subject)[:180]  # magic-number-allow: string-truncation-cap
            summary = (request.POST.get("incident_summary") or "").strip()[:4000]  # magic-number-allow: ai-message-char-cap
            sev_raw = (request.POST.get("incident_severity") or "MINOR").strip().upper()
            severity = sev_raw if sev_raw in dict(PublicIncident.Severity.choices) else PublicIncident.Severity.MINOR
            stat_raw = (request.POST.get("incident_status") or "INVESTIGATING").strip().upper()
            status = stat_raw if stat_raw in dict(PublicIncident.Status.choices) else PublicIncident.Status.INVESTIGATING
            existing = ticket.public_incidents.filter(status__in=["INVESTIGATING", "IDENTIFIED", "MONITORING"]).first()
            if existing is not None:
                existing.title = title
                existing.summary = summary
                existing.severity = severity
                existing.status = status
                if status == PublicIncident.Status.RESOLVED and not existing.resolved_at:
                    existing.resolved_at = timezone.now()
                existing.save()
                messages.success(request, f"Public incident #{existing.pk} updated.")
            else:
                PublicIncident.objects.create(
                    source_ticket=ticket,
                    title=title,
                    summary=summary,
                    severity=severity,
                    status=status,
                    promoted_by=request.user,
                    started_at=ticket.created_at or timezone.now(),
                )
                messages.success(request, "Promoted to a public incident on /status/.")
            return redirect("super:support_ticket_detail", ticket_id=ticket.pk)

        # v4.00.42 — incident link / duplicate merge.
        if action == "link":
            parent_raw = (request.POST.get("parent_ticket_id") or "").strip()
            if not parent_raw:
                ticket.linked_to = None
                ticket.save(update_fields=["linked_to"])
                messages.success(request, "Removed parent link.")
            else:
                # tenant-isolation-allow: super-operator-link-incident-cross-tenant-by-design
                parent = GlobalSupportTicket.objects.filter(pk=parent_raw).first()
                if parent is None or parent.pk == ticket.pk:
                    messages.error(request, "Invalid parent ticket.")
                else:
                    ticket.linked_to = parent
                    ticket.save(update_fields=["linked_to"])
                    messages.success(request, f"Linked to parent {parent.pk}.")
            return redirect("super:support_ticket_detail", ticket_id=ticket.pk)
        if action == "merge":
            target_raw = (request.POST.get("merge_target_id") or "").strip()
            if not target_raw:
                ticket.merged_into = None
                ticket.save(update_fields=["merged_into"])
                messages.success(request, "Unmarked as duplicate.")
            else:
                # tenant-isolation-allow: super-operator-merge-duplicate-cross-tenant-by-design
                target = GlobalSupportTicket.objects.filter(pk=target_raw).first()
                if target is None or target.pk == ticket.pk:
                    messages.error(request, "Invalid merge target.")
                else:
                    ticket.merged_into = target
                    if ticket.status not in (
                        GlobalSupportTicket.Status.CLOSED,
                        GlobalSupportTicket.Status.RESOLVED,
                    ):
                        ticket.status = GlobalSupportTicket.Status.CLOSED
                    ticket.save(update_fields=["merged_into", "status"])
                    messages.success(
                        request, f"Marked as duplicate of {target.pk}; ticket closed."
                    )
            return redirect("super:support_ticket_detail", ticket_id=ticket.pk)

        changed: list[str] = []
        new_status = request.POST.get("status", "").strip().upper()
        if new_status and new_status in GlobalSupportTicket.Status.values:
            if new_status != ticket.status:
                from apps.siteconfig.support_fsm import (
                    InvalidTransition,
                    validate_transition,
                )
                try:
                    validate_transition(ticket.status, new_status)
                except InvalidTransition as exc:
                    messages.error(request, f"Status change rejected: {exc}")
                    return redirect("super:support_ticket_detail", ticket_id=ticket.pk)
                ticket.status = new_status
                changed.append("status")
        raw_notes = request.POST.get("internal_notes", "")
        if isinstance(raw_notes, str) and raw_notes != ticket.internal_notes:
            ticket.internal_notes = raw_notes[:32000]  # magic-number-allow: text-body-char-truncation-cap
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

    from apps.siteconfig.models_feature_controls import PublicIncident
    from apps.siteconfig.support_fsm import allowed_next as _fsm_allowed_next

    active_public_incident = ticket.public_incidents.exclude(
        status=PublicIncident.Status.RESOLVED
    ).order_by("-started_at").first()

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
            "allowed_next_statuses": list(_fsm_allowed_next(ticket.status)),
            "incident_severity_choices": PublicIncident.Severity.choices,
            "incident_status_choices": PublicIncident.Status.choices,
            "active_public_incident": active_public_incident,
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

    # v4.00.42 — sparkline: last 12 months in chronological order, inline SVG path.
    sparkline_months = list(reversed(by_month[:12]))
    sparkline_svg = ""
    sparkline_range = {"min": None, "max": None}
    if sparkline_months:
        scores = [float(m["avg_score"] or 0) for m in sparkline_months]
        min_s = min(scores)
        max_s = max(scores)
        sparkline_range = {"min": round(min_s, 2), "max": round(max_s, 2)}
        # Build a 0..1 normalized polyline; SVG viewBox = 120 x 32.
        width = 120
        height = 32
        if len(scores) > 1 and max_s > min_s:
            steps = len(scores) - 1
            points = []
            for idx, score in enumerate(scores):
                x = round((idx / steps) * width, 2)
                y = round(height - ((score - min_s) / (max_s - min_s)) * height, 2)
                points.append(f"{x},{y}")
            polyline = " ".join(points)
        else:
            polyline = f"0,{height // 2} {width},{height // 2}"
        sparkline_svg = (
            f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            'role="img" aria-label="CSAT trend">'
            f'<polyline fill="none" stroke="currentColor" stroke-width="1.6" points="{polyline}"/>'
            "</svg>"
        )

    return render(
        request,
        "schools/super_support_csat_dashboard.html",
        {
            "overall_avg": overall.get("avg"),
            "overall_n": overall.get("n") or 0,
            "by_month": by_month,
            "recent": recent,
            "sparkline_svg": sparkline_svg,
            "sparkline_range": sparkline_range,
            "sparkline_count": len(sparkline_months),
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def support_bulk_action(request):
    """v4.00.37 — POST a bulk action across the selected ticket ids.

    Accepts: action (assign_me / in_progress / waiting / resolve / escalate),
    ticket_ids (multi-valued). Validates each transition and writes a structured
    audit entry to ticket.metadata['transitions']. Returns JSON for the queue's
    JS listener to re-trigger the HTMX fragment refresh.
    """
    from django.http import JsonResponse

    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    action = (request.POST.get("action") or "").strip().lower()
    ticket_ids = [tid for tid in request.POST.getlist("ticket_ids") if tid.strip()]
    if not action or not ticket_ids:
        return JsonResponse({"error": "missing_fields"}, status=400)

    valid_actions = {"assign_me", "in_progress", "waiting", "resolve", "escalate"}
    if action not in valid_actions:
        return JsonResponse({"error": "unknown_action"}, status=400)

    from apps.siteconfig.support_fsm import (
        InvalidTransition,
        can_transition,
        validate_transition,
    )

    actor = request.user
    updated = 0
    skipped = 0
    invalid_transitions: list[str] = []
    # tenant-isolation-allow: super-operator-bulk-action-cross-tenant-by-design
    queryset = GlobalSupportTicket.objects.filter(pk__in=ticket_ids)
    for ticket in queryset:
        before_status = ticket.status
        before_priority = ticket.priority
        before_assigned = ticket.assigned_to_id
        try:
            # v4.00.42 — FSM-guarded transitions.
            if action == "assign_me":
                ticket.assigned_to = actor
                if ticket.status == GlobalSupportTicket.Status.OPEN and can_transition(
                    before_status, GlobalSupportTicket.Status.IN_PROGRESS
                ):
                    ticket.status = GlobalSupportTicket.Status.IN_PROGRESS
            elif action == "in_progress":
                validate_transition(before_status, GlobalSupportTicket.Status.IN_PROGRESS)
                ticket.status = GlobalSupportTicket.Status.IN_PROGRESS
            elif action == "waiting":
                validate_transition(before_status, GlobalSupportTicket.Status.WAITING)
                ticket.status = GlobalSupportTicket.Status.WAITING
            elif action == "resolve":
                validate_transition(before_status, GlobalSupportTicket.Status.RESOLVED)
                ticket.status = GlobalSupportTicket.Status.RESOLVED
            elif action == "escalate":
                if ticket.priority == GlobalSupportTicket.Priority.LOW:
                    ticket.priority = GlobalSupportTicket.Priority.NORMAL
                elif ticket.priority == GlobalSupportTicket.Priority.NORMAL:
                    ticket.priority = GlobalSupportTicket.Priority.HIGH
                else:
                    ticket.priority = GlobalSupportTicket.Priority.URGENT
            metadata = dict(ticket.metadata or {})
            transitions = list(metadata.get("transitions") or [])
            transitions.append(
                {
                    "actor_id": getattr(actor, "id", None),
                    "action": action,
                    "before": {
                        "status": before_status,
                        "priority": before_priority,
                        "assigned_to_id": before_assigned,
                    },
                    "after": {
                        "status": ticket.status,
                        "priority": ticket.priority,
                        "assigned_to_id": ticket.assigned_to_id,
                    },
                    "at": timezone.now().isoformat(),
                }
            )
            metadata["transitions"] = transitions[-50:]
            ticket.metadata = metadata
            ticket.save(
                update_fields=[
                    "status",
                    "priority",
                    "assigned_to",
                    "metadata",
                    "updated_at",
                ]
            )
            updated += 1
        except InvalidTransition as exc:
            skipped += 1
            invalid_transitions.append(f"{ticket.pk}: {exc}")
            continue
        except Exception:  # noqa: BLE001 — best-effort batch
            skipped += 1

    detail = f"{updated} updated"
    if skipped:
        detail += f" ({skipped} skipped)"
    response = {"ok": True, "updated": updated, "skipped": skipped, "detail": detail}
    if invalid_transitions:
        response["invalid_transitions"] = invalid_transitions[:10]
    return JsonResponse(response)
