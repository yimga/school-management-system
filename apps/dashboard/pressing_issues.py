"""
Pressing Issues — single-pane-of-glass widget builders.

Two entry points:
  build_operator_pressing_issues(request) → fleet-wide operator surface
  build_tenant_pressing_issues(request)   → school-scoped tenant surface

Each returns a dict consumed by ``partials/pressing_issues_pane.html``.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, OperationalError
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

_SOFT_FAILURES = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    ObjectDoesNotExist,
    ValidationError,
    DatabaseError,
    OperationalError,
    NoReverseMatch,
)


def _safe_reverse(name: str, kwargs=None, fallback: str = "") -> str:
    try:
        return reverse(name, kwargs=kwargs)
    except (NoReverseMatch, ValueError, TypeError):
        return fallback


def _metric(
    key: str,
    label: str,
    count: int,
    url: str,
    *,
    tone: str = "info",
    hint: str = "",
) -> dict:
    return {
        "key": key,
        "label": label,
        "count": count,
        "url": url,
        "tone": tone,
        "hint": hint,
    }


def _item(
    title: str,
    meta: str,
    url: str,
    *,
    tone: str = "info",
    badge: str = "",
) -> dict:
    return {
        "title": title,
        "meta": meta,
        "url": url,
        "tone": tone,
        "badge": badge,
    }


def _tone_for_count(count: int, warn_at: int = 1, danger_at: int = 5) -> str:
    if count >= danger_at:
        return "danger"
    if count >= warn_at:
        return "warning"
    if count > 0:
        return "info"
    return "muted"


# ---------------------------------------------------------------------------
# Operator builder (fleet-wide, manager host / /super/)
# ---------------------------------------------------------------------------


def build_operator_pressing_issues(request) -> dict:
    """Fleet-wide pressing items for manager/operator dashboards."""
    metrics: list[dict] = []
    items: list[dict] = []

    support_url = _safe_reverse("super:support_dashboard")
    command_center_url = _safe_reverse("super:command_center")
    incidents_url = _safe_reverse("super:incidents_list")

    support_open = 0
    support_urgent = 0
    support_backlog_48h = 0
    trial_ending = 0
    churn_risk = 0
    provisioning_breaches = 0
    stale_rows: list = []

    try:
        from apps.schools.super_views_command_center_data import (
            build_command_center_data,
        )

        cc = build_command_center_data()
        support_open = int(cc.get("support_open_count", 0) or 0)
        support_backlog_48h = int(cc.get("support_backlog_48h_count", 0) or 0)
        trial_ending = int(cc.get("trial_ending_soon_count", 0) or 0)
        churn_risk = int(cc.get("tenant_churn_risk_count", 0) or 0)
        provisioning_breaches = int(cc.get("provisioning_sla_breaches", 0) or 0)
        stale_rows = list(cc.get("support_stale_rows", []) or [])
    except _SOFT_FAILURES:
        logger.debug("pressing_issues: command center data unavailable", exc_info=True)

    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        # tenant-isolation-allow: operator-fleet-wide-support-dashboard-scoped
        support_urgent = GlobalSupportTicket.objects.filter(
            status__in=("OPEN", "IN_PROGRESS", "WAITING"),
            priority="URGENT",
        ).count()
    except Exception:
        logger.debug("pressing_issues: urgent ticket count unavailable", exc_info=True)

    if support_url:
        metrics.append(
            _metric(
                "support_open",
                _("Open tickets"),
                support_open,
                f"{support_url}?status=OPEN",
                tone=_tone_for_count(support_open, warn_at=3, danger_at=10),
                hint=_("All open support tickets across the fleet"),
            )
        )
        metrics.append(
            _metric(
                "support_urgent",
                _("Urgent"),
                support_urgent,
                f"{support_url}?priority=URGENT",
                tone=_tone_for_count(support_urgent),
                hint=_("Urgent priority tickets"),
            )
        )
    if support_url or command_center_url:
        metrics.append(
            _metric(
                "support_backlog_48h",
                _("Backlog 48h+"),
                support_backlog_48h,
                command_center_url or support_url,
                tone=_tone_for_count(support_backlog_48h, warn_at=1, danger_at=3),
                hint=_("Support tickets older than 48 hours"),
            )
        )
    if incidents_url:
        incident_count = 0
        try:
            from apps.observability.monitoring import PlatformIncident

            # tenant-isolation-allow: operator-fleet-wide-incident-dashboard-scoped
            incident_count = PlatformIncident.objects.filter(
                status__in=("open", "acknowledged"),
            ).count()
        except Exception:
            # Optional metric — never fail the pane if observability models are absent.
            logger.debug("pressing_issues: incident count unavailable", exc_info=True)
        metrics.append(
            _metric(
                "platform_incidents",
                _("Incidents"),
                incident_count,
                incidents_url,
                tone=_tone_for_count(incident_count),
                hint=_("Active platform incidents"),
            )
        )
    if command_center_url:
        metrics.append(
            _metric(
                "provisioning_breaches",
                _("SLA breaches"),
                provisioning_breaches,
                command_center_url,
                tone=_tone_for_count(provisioning_breaches),
                hint=_("Provisioning SLA target exceeded"),
            )
        )
        metrics.append(
            _metric(
                "trial_ending",
                _("Trial ending"),
                trial_ending,
                command_center_url,
                tone=_tone_for_count(trial_ending, warn_at=1, danger_at=3),
                hint=_("Trials ending within 7 days"),
            )
        )
        metrics.append(
            _metric(
                "churn_risk",
                _("Churn risk"),
                churn_risk,
                command_center_url,
                tone=_tone_for_count(churn_risk, warn_at=1, danger_at=3),
                hint=_("Tenants flagged as churn-risk"),
            )
        )

    for row in stale_rows[:5]:
        ticket = row.get("ticket")
        if not ticket:
            continue
        age_h = round(float(row.get("age_hours", 0)), 1)
        ticket_url = _safe_reverse(
            "super:support_ticket_detail",
            kwargs={"pk": str(ticket.pk)},
        )
        items.append(
            _item(
                title=str(getattr(ticket, "subject", ""))[:80] or _("Support ticket"),
                meta=_("%(hours)s hours old") % {"hours": age_h},
                url=ticket_url or support_url,
                tone="danger" if age_h >= 168 else "warning",
                badge=str(getattr(ticket, "priority", "")),
            )
        )

    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        # tenant-isolation-allow: operator-fleet-wide-urgent-ticket-list-scoped
        urgent_tickets = list(
            GlobalSupportTicket.objects.filter(
                status__in=("OPEN", "IN_PROGRESS", "WAITING"),
                priority="URGENT",
            )
            .select_related("school")
            .order_by("created_at")[:5]
        )
        seen_ids = {
            str(getattr(row.get("ticket"), "pk", None))
            for row in stale_rows[:5]
            if row.get("ticket")
        }
        for ticket in urgent_tickets:
            if str(ticket.pk) in seen_ids:
                continue
            if len(items) >= 8:
                break
            ticket_url = _safe_reverse(
                "super:support_ticket_detail",
                kwargs={"pk": str(ticket.pk)},
            )
            school_name = str(getattr(ticket.school, "name", ""))[:40] if ticket.school else ""
            items.append(
                _item(
                    title=str(ticket.subject)[:80] or _("Support ticket"),
                    meta=school_name or _("Fleet-wide"),
                    url=ticket_url or support_url,
                    tone="danger",
                    badge="URGENT",
                )
            )
    except Exception:
        logger.debug("pressing_issues: urgent ticket list unavailable", exc_info=True)

    final_items = items[:8]
    has_pressure = bool(final_items) or any(int(m.get("count") or 0) > 0 for m in metrics)
    return {
        "title": _("Pressing issues"),
        "subtitle": _("Fleet-wide items that need attention now"),
        "scope": "operator",
        "metrics": metrics,
        "items": final_items,
        "show_empty": not has_pressure,
        "empty_message": _("No pressing issues across the fleet right now."),
        "primary_cta": {
            "label": _("Command center"),
            "url": command_center_url or support_url or _safe_reverse("super:dashboard"),
        },
    }


# ---------------------------------------------------------------------------
# Tenant builder (school-scoped, portal / backend)
# ---------------------------------------------------------------------------


def build_tenant_pressing_issues(request) -> dict:
    """School-scoped pressing items for tenant backend dashboard."""
    school = getattr(request, "school", None)
    user = getattr(request, "user", None)
    metrics: list[dict] = []
    items: list[dict] = []

    support_hub_url = _safe_reverse("portal:support_help_hub")
    support_request_url = _safe_reverse("portal:support_request")
    requests_url = _safe_reverse("requests:dashboard")
    finance_url = _safe_reverse("finance:dashboard")

    admin_roles = {
        "ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL",
        "IT_ADMIN", "HOD", "DEPT_LEAD", "PROPRIETOR", "SUPERADMIN",
    }
    role_code = (getattr(user, "role", "") or "").upper() if user else ""
    is_elevated = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or role_code in admin_roles
    )

    # -- Support tickets --
    open_tickets = 0
    ticket_rows: list = []
    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        if school:
            base_qs = GlobalSupportTicket.objects.filter(
                school=school,
                status__in=("OPEN", "IN_PROGRESS", "WAITING"),
            )
            if is_elevated:
                ticket_qs = base_qs
            else:
                ticket_qs = base_qs.filter(user=user) if user else base_qs.none()
            open_tickets = ticket_qs.count()
            ticket_rows = list(ticket_qs.order_by("-created_at")[:5])
    except _SOFT_FAILURES:
        pass

    metrics.append(
        _metric(
            "support_open",
            _("Open tickets"),
            open_tickets,
            support_hub_url or support_request_url,
            tone=_tone_for_count(open_tickets, warn_at=1, danger_at=5),
            hint=_("Support tickets awaiting resolution"),
        )
    )

    # -- Pending access requests --
    pending_access = 0
    try:
        from apps.requests.models import AccessRequest

        if school:
            pending_access = AccessRequest.objects.filter(
                school=school,
                status=AccessRequest.Status.PENDING,
            ).count()
    except _SOFT_FAILURES:
        pass

    if requests_url:
        metrics.append(
            _metric(
                "pending_access",
                _("Pending requests"),
                pending_access,
                requests_url,
                tone=_tone_for_count(pending_access),
                hint=_("Access requests awaiting approval"),
            )
        )

    # -- Overdue invoices --
    overdue_invoices = 0
    try:
        from apps.finance.models import Invoice

        if school:
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            overdue_invoices = Invoice.objects.filter(
                school=school, status="OVERDUE"
            ).count()
    except _SOFT_FAILURES:
        pass

    if finance_url:
        metrics.append(
            _metric(
                "overdue_invoices",
                _("Overdue invoices"),
                overdue_invoices,
                finance_url,
                tone=_tone_for_count(overdue_invoices, warn_at=1, danger_at=3),
                hint=_("Invoices past their due date"),
            )
        )

    # -- Unread messages --
    unread_messages = 0
    messages_url = _safe_reverse("accounts:user_messages")
    try:
        from apps.communication.models import Message

        if user and user.is_authenticated:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            msg_qs = Message.objects.filter(recipient=user, is_read=False)
            if school is not None:
                msg_qs = msg_qs.filter(school=school)
            unread_messages = msg_qs.count()
    except _SOFT_FAILURES:
        pass

    if messages_url:
        metrics.append(
            _metric(
                "unread_messages",
                _("Unread messages"),
                unread_messages,
                messages_url,
                tone=_tone_for_count(unread_messages, warn_at=3, danger_at=10),
                hint=_("Messages you haven't read yet"),
            )
        )

    # -- Ticket items --
    for ticket in ticket_rows[:6]:
        ticket_url = _safe_reverse(
            "portal:support_ticket_detail",
            kwargs={"pk": str(ticket.pk)},
        )
        priority_str = str(getattr(ticket, "priority", "NORMAL"))
        tone = "danger" if priority_str == "URGENT" else (
            "warning" if priority_str == "HIGH" else "info"
        )
        items.append(
            _item(
                title=str(ticket.subject)[:80] or _("Support ticket"),
                meta=str(getattr(ticket, "get_status_display", lambda: ticket.status)()),
                url=ticket_url or support_hub_url or support_request_url,
                tone=tone,
                badge=priority_str,
            )
        )

    # -- Pending approvals as items --
    if pending_access > 0 and requests_url:
        items.append(
            _item(
                title=_("%(count)s pending access request(s)") % {"count": pending_access},
                meta=_("Awaiting admin approval"),
                url=requests_url,
                tone="warning",
                badge=_("Pending"),
            )
        )

    final_items = items[:8]
    has_pressure = bool(final_items) or any(int(m.get("count") or 0) > 0 for m in metrics)
    return {
        "title": _("Pressing issues"),
        "subtitle": _("Items that need your attention"),
        "scope": "tenant",
        "metrics": metrics,
        "items": final_items,
        "show_empty": not has_pressure,
        "empty_message": _("Nothing pressing right now — your school is running smoothly."),
        "primary_cta": {
            "label": _("Support hub"),
            "url": support_hub_url or support_request_url or _safe_reverse("accounts:backend_dashboard"),
        },
    }
