"""Owner Console — Support (one front door for help, tickets and knowledge).

Wave 7.4. The tenant already has a unified help center (``feedback:help_center``),
a knowledge base (``kb:``), and real support tickets (``GlobalSupportTicket``). What
the Owner Console lacked was an entry to them — so an owner had no in-console place
to see their school's open tickets or reach help.

This section surfaces the school's open-ticket count and the owner's recent tickets,
then deep-links the existing surfaces via the canonical ``support_entry_points`` map
(the same SOT the help center itself uses). It authors nothing — it's a router with
context — owner-gated, tenant-skinned and fail-soft.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.accounts.views_owner_console import _owner_only
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)

_SOFT = Exception


def _support_links(request) -> dict:
    """The canonical help/contact/KB URL map, fail-soft to an empty dict."""
    try:
        from apps.feedback.services import support_entry_points

        return support_entry_points(request) or {}
    except _SOFT as exc:  # noqa: BLE001 — links degrade to none, never 500
        logger.debug("owner console support links failed: %s", exc)
        return {}


def _my_tickets_and_counts(request):
    """The owner's recent tickets + open count for this school. Fail-soft."""
    tickets: list = []
    open_count = 0
    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        school = request.school
        base = GlobalSupportTicket.objects.filter(school=school, user=request.user)
        for t in base.order_by("-created_at")[:8]:
            tickets.append(
                {
                    "subject": getattr(t, "subject", "") or "",
                    "status": (getattr(t, "status", "") or "").replace("_", " ").title(),
                    "priority": (getattr(t, "priority", "") or "").title(),
                    "when": getattr(t, "created_at", None),
                }
            )
        try:
            open_statuses = (
                GlobalSupportTicket.Status.OPEN,
                GlobalSupportTicket.Status.IN_PROGRESS,
                GlobalSupportTicket.Status.WAITING,
            )
            open_count = base.filter(status__in=open_statuses).count()
        except _SOFT:  # noqa: BLE001 — enum shape drift → fall back to all non-closed
            open_count = base.exclude(status__icontains="closed").count()
    except _SOFT as exc:  # noqa: BLE001 — panel degrades to empty, never 500s
        logger.debug("owner console support tickets failed: %s", exc)
    return tickets, open_count


@login_required
@require_school
def owner_console_support(request):
    """Support — help, tickets and knowledge in one place (owner-gated)."""
    ctx, denied = _owner_only(request, "support")
    if denied:
        return denied

    links = _support_links(request)
    tickets, open_count = _my_tickets_and_counts(request)
    ctx.update(
        {
            "support_links": links,
            "my_tickets": tickets,
            "open_ticket_count": open_count,
            # named deep-links the template reads directly (all fail-soft to "")
            "help_center_url": links.get("help_center", ""),
            "new_ticket_url": links.get("support_request", ""),
            "kb_url": links.get("kb_home", ""),
            "faq_url": links.get("faq_list", ""),
            "contact_url": links.get("contact_center", ""),
        }
    )
    return render(request, "accounts/owner_console/support.html", ctx)
