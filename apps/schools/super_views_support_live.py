"""Operator ("agent-side") live support console — the /super/ half of the
human support live-chat loop.

The customer's ``SupportChatConsumer`` (apps/api/consumers.py) persists each
inbound line as a submitter-visible reply on their open ``GlobalSupportTicket``
and broadcasts it to a private ``support_chat_{school}_{user}`` room. This page
is where a platform support agent watches those rooms and answers live: it
renders the actionable ticket queue and boots the ``SupportAgentConsumer``
WebSocket client (``static/js/support-agent-console.js``), which subscribes to a
ticket's room and posts operator replies back into it.

Gated exactly like the rest of ``/super/support`` — ``require_platform_scope``
(control-plane access + ``team.read``), NOT Django ``is_staff`` — so tenant staff
can never reach it. The operator is not tenant-bound; cross-tenant visibility
here is the whole point of a platform support desk and is scope-gated, mirroring
``super_support_dashboard``.
"""

from __future__ import annotations

from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TEAM_READ,
    require_platform_scope,
)

_LIVE_CONSOLE_QUEUE_LIMIT = 100  # magic-number-allow: live-support-console-queue-cap


def _actor_display(user) -> str:
    """Short, human-readable label for a ticket's submitter/assignee."""
    if user is None:
        return ""
    full = (user.get_full_name() or "").strip()
    return full or user.get_username()


@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def super_support_live_console(request):
    """Operator live-chat console: actionable ticket queue + agent WS client."""
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    actionable = [
        GlobalSupportTicket.Status.OPEN,
        GlobalSupportTicket.Status.IN_PROGRESS,
        GlobalSupportTicket.Status.WAITING,
    ]
    # Cross-tenant by design: a platform support desk answers every school's
    # tickets. GlobalSupportTicket is a public/shared-schema model (not tenant
    # RLS-scoped), same as super_support_dashboard's queue. user__isnull=False:
    # a live chat needs a live customer to talk back to.
    rows = (
        # tenant-isolation-allow: platform-support-console-cross-tenant-operator-team-read-gated
        GlobalSupportTicket.objects.filter(
            status__in=actionable, user__isnull=False
        )
        .select_related("school", "user", "assigned_to")
        .order_by("-updated_at")[:_LIVE_CONSOLE_QUEUE_LIMIT]
    )

    live_tickets = []
    for ticket in rows:
        meta = ticket.metadata or {}
        live_tickets.append(
            {
                "id": str(ticket.pk),
                "subject": ticket.subject,
                "status": ticket.status,
                "status_label": ticket.get_status_display(),
                "priority": ticket.priority,
                "school_name": getattr(ticket.school, "name", "") or "",
                "user_display": _actor_display(ticket.user),
                "assigned_display": _actor_display(ticket.assigned_to),
                "is_live_chat": (meta.get("channel") == "live_chat"),
                "updated_at": ticket.updated_at,
            }
        )

    context = {
        "cp_page_title": _("Live support console"),
        "live_tickets": live_tickets,
        "live_open_count": len(live_tickets),
    }
    return render(request, "schools/super_support_live_console.html", context)
