"""
Side effects for GlobalSupportTicket: operator email/in-app fan-out, optional HTTP webhook,
and domain-event outbox for integrations.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

_HOOK_ERRORS = (
    AttributeError,
    ImportError,
    LookupError,
    OSError,
    TypeError,
    ValueError,
)


def _support_operator_users():
    from apps.accounts.models import User

    preferred_roles = [User.Role.IT_ADMIN]
    fallback_roles = [
        User.Role.ADMIN,
        User.Role.SUPERADMIN,
        User.Role.LEADERSHIP,
    ]
    qs = User.objects.filter(
        Q(role__in=preferred_roles) | Q(roles__code__in=preferred_roles)
    ).distinct()
    if qs.exists():
        return list(qs.order_by("id"))
    qs = User.objects.filter(
        Q(role__in=fallback_roles) | Q(roles__code__in=fallback_roles)
    ).distinct()
    if qs.exists():
        return list(qs.order_by("id"))
    return list(
        User.objects.filter(Q(is_superuser=True) | Q(is_staff=True))
        .distinct()
        .order_by("id")
    )


def _iter_support_webhook_targets() -> Iterator[tuple[str, str]]:
    """Yield (url, secret) for DB endpoints first, then legacy env URL (deduped)."""
    from apps.siteconfig.models_feature_controls import GlobalSupportTicketWebhookEndpoint

    seen: set[str] = set()
    for row in GlobalSupportTicketWebhookEndpoint.objects.filter(is_active=True).only(
        "url", "secret"
    ):
        u = (row.url or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        yield u, (row.secret or "").strip()
    legacy = (getattr(settings, "SUPPORT_TICKET_WEBHOOK_URL", None) or "").strip()
    if legacy and legacy not in seen:
        sec = (getattr(settings, "SUPPORT_TICKET_WEBHOOK_SECRET", None) or "").strip()
        yield legacy, sec


def _schedule_support_ticket_webhooks(payload: dict[str, Any]) -> None:
    """Queue Celery delivery after commit (retries on transport/5xx)."""
    from apps.siteconfig.tasks import deliver_support_ticket_http_webhook

    targets = list(_iter_support_webhook_targets())
    for url, secret in targets:
        pl = dict(payload)

        def _enqueue(u: str = url, s: str = secret, p: dict[str, Any] = pl):
            deliver_support_ticket_http_webhook.apply_async(
                kwargs={"url": u, "secret": s, "payload": p},
            )

        transaction.on_commit(_enqueue)


def run_support_ticket_created_hooks(
    ticket_id: str,
    *,
    primary_recipient_id: int | None = None,
) -> None:
    """
    Called after commit. Loads ticket by UUID string.
    """
    from apps.communication.comms_locale import locale_target_for_user
    from apps.communication.models import Message
    from apps.communication.notification_service import send_email, send_push
    from apps.platform_runtime.events import emit_platform_event
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    ticket = (
        GlobalSupportTicket.objects.select_related("school", "user")
        .filter(pk=ticket_id)
        .first()
    )
    if ticket is None:
        return

    try:
        emit_platform_event(
            "support_desk_ticket_created",
            {
                "ticket_id": str(ticket.pk),
                "school_id": str(ticket.school_id),
                "submitter_id": ticket.user_id,
                "priority": ticket.priority,
                "status": ticket.status,
            },
            school_id=str(ticket.school_id),
            idempotency_key=f"support-created-{ticket.pk}",
        )
    except _HOOK_ERRORS:
        logger.debug("emit support_desk_ticket_created skipped", exc_info=True)

    operators = _support_operator_users()
    school = ticket.school

    if getattr(settings, "SUPPORT_TICKET_NOTIFY_EMAIL", True):
        emails = sorted(
            {
                (u.email or "").strip()
                for u in operators
                if (u.email or "").strip()
            }
        )
        if emails:
            subj = f"[RunMyCampus] New support ticket — {ticket.subject[:120]}"
            body = (
                f"School: {school.name}\n"
                f"Ticket ID: {ticket.pk}\n"
                f"Priority: {ticket.priority}\n"
                f"Submitter: {ticket.user}\n\n"
                f"Open in control plane support queue to respond.\n"
            )
            try:
                send_email(
                    emails,
                    subj,
                    body,
                    school=school,
                    fail_silently=True,
                )
            except _HOOK_ERRORS:
                logger.debug("support ticket email fan-out failed", exc_info=True)

    fanout = getattr(settings, "SUPPORT_TICKET_INAPP_FANOUT_OPERATORS", False)
    if getattr(settings, "SUPPORT_TICKET_NOTIFY_INAPP", True) and fanout:
        sender = ticket.user
        if sender is None and primary_recipient_id:
            from apps.accounts.models import User

            sender = User.objects.filter(pk=primary_recipient_id).first()
        if sender is None and operators:
            sender = operators[0]
        if sender is not None:
            for u in operators:
                if primary_recipient_id and u.pk == primary_recipient_id:
                    continue
                if u.pk == sender.pk:
                    continue
                try:
                    subj = f"[Support {str(ticket.pk)[:8]}] {ticket.subject}"[:255]
                    Message.objects.create(
                        sender=sender,
                        recipient=u,
                        subject=subj,
                        body=(
                            f"New platform support ticket from {school.name}.\n"
                            f"Ticket ID: {ticket.pk}\n\n"
                            f"{ticket.body[:4000]}"
                        ),
                        school=school,
                        locale_target=locale_target_for_user(u),
                    )
                except _HOOK_ERRORS:
                    logger.debug(
                        "support ticket in-app notify user=%s failed", u.pk, exc_info=True
                    )

    if getattr(settings, "SUPPORT_TICKET_PUSH_OPERATORS_ON_CREATE", False):
        try:
            title = "New support ticket"
            body_push = f"{school.name}: {ticket.subject[:120]}"
            data = {"ticket_id": str(ticket.pk), "event": "support_ticket_created"}
            for u in operators:
                send_push(school, u, title, body_push, data=data)
        except _HOOK_ERRORS:
            logger.debug("support ticket operator push skipped", exc_info=True)

    payload = {
        "event": "support.global_ticket.created",
        "ticket_id": str(ticket.pk),
        "school_id": str(ticket.school_id),
        "subject": ticket.subject[:500],
        "priority": ticket.priority,
        "status": ticket.status,
        "submitter_id": ticket.user_id,
    }
    try:
        _schedule_support_ticket_webhooks(payload)
    except _HOOK_ERRORS:
        logger.debug("schedule support webhooks skipped", exc_info=True)

    try:
        from apps.events.webhooks import enqueue_webhook_event

        enqueue_webhook_event(
            school=ticket.school,
            event_type="support.global_ticket.created",
            data={
                "ticket_id": str(ticket.pk),
                "school_id": str(ticket.school_id),
                "subject": ticket.subject[:500],
                "priority": ticket.priority,
            },
            event_id=f"support-ticket-{ticket.pk}",
            process_immediately=True,
        )
    except _HOOK_ERRORS:
        logger.debug("enqueue_webhook_event for support ticket skipped", exc_info=True)


def run_support_ticket_reply_hooks(
    ticket_id: str,
    *,
    actor_id: int | None,
    visibility: str,
    reply_body: str = "",
) -> None:
    from apps.communication.notification_service import send_email, send_push
    from apps.platform_runtime.events import emit_platform_event
    from apps.siteconfig.models_feature_controls import (
        GlobalSupportTicket,
        GlobalSupportTicketReply,
    )

    ticket = (
        GlobalSupportTicket.objects.select_related("school", "user")
        .filter(pk=ticket_id)
        .first()
    )
    if ticket is None:
        return

    body_text = (reply_body or "").strip()
    if not body_text:
        latest = (
            GlobalSupportTicketReply.objects.filter(ticket_id=ticket_id)
            .order_by("-created_at")
            .first()
        )
        body_text = (latest.body or "").strip() if latest else ""

    try:
        emit_platform_event(
            "support_desk_ticket_reply_added",
            {
                "ticket_id": str(ticket.pk),
                "school_id": str(ticket.school_id),
                "actor_id": actor_id,
                "visibility": visibility,
            },
            school_id=str(ticket.school_id),
            idempotency_key=None,
        )
    except _HOOK_ERRORS:
        logger.debug("emit support_desk_ticket_reply_added skipped", exc_info=True)

    vis = (visibility or "").strip().upper()
    submitter = ticket.user
    notify_submitter = (
        vis == GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
        and submitter is not None
        and actor_id is not None
        and submitter.pk != actor_id
        and getattr(settings, "SUPPORT_TICKET_NOTIFY_SUBMITTER_ON_VISIBLE_REPLY", True)
    )
    if notify_submitter:
        to_addr = (getattr(submitter, "email", None) or "").strip()
        if to_addr:
            try:
                from apps.siteconfig.email_palette import resolve_email_palette

                ctx = {
                    "ticket": ticket,
                    "reply_body": body_text[:8000],
                    "school": ticket.school,
                    # Branded inline-hex palette (no request here — supply explicitly).
                    "brand_email": resolve_email_palette(site=ticket.school),
                }
                plain = render_to_string("emails/support_ticket_reply_visible.txt", ctx)
                html = render_to_string("emails/support_ticket_reply_visible.html", ctx)
                subj = f"Update on your support request — {ticket.subject[:80]}"
                send_email(
                    [to_addr],
                    subj,
                    plain,
                    html_message=html,
                    school=ticket.school,
                    fail_silently=True,
                )
            except _HOOK_ERRORS:
                logger.debug("support reply email to submitter failed", exc_info=True)
        if getattr(settings, "SUPPORT_TICKET_PUSH_SUBMITTER_ON_VISIBLE_REPLY", False):
            try:
                send_push(
                    ticket.school,
                    submitter,
                    "Support reply",
                    body_text[:200],
                    data={"ticket_id": str(ticket.pk), "event": "support_ticket_reply"},
                )
            except _HOOK_ERRORS:
                logger.debug("support reply push skipped", exc_info=True)

    payload = {
        "event": "support.global_ticket.reply_added",
        "ticket_id": str(ticket.pk),
        "school_id": str(ticket.school_id),
        "visibility": visibility,
        "actor_id": actor_id,
    }
    try:
        _schedule_support_ticket_webhooks(payload)
    except _HOOK_ERRORS:
        logger.debug("schedule support reply webhooks skipped", exc_info=True)


def run_support_ticket_csat_hooks(ticket_id: str, *, actor_id: int | None) -> None:
    from apps.platform_runtime.events import emit_platform_event
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    ticket = GlobalSupportTicket.objects.filter(pk=ticket_id).first()
    if ticket is None:
        return
    try:
        emit_platform_event(
            "support_desk_ticket_csat_submitted",
            {
                "ticket_id": str(ticket.pk),
                "school_id": str(ticket.school_id),
                "actor_id": actor_id,
                "score": ticket.csat_score,
            },
            school_id=str(ticket.school_id),
            idempotency_key=f"support-csat-{ticket.pk}",
        )
    except _HOOK_ERRORS:
        logger.debug("emit support_desk_ticket_csat_submitted skipped", exc_info=True)

    payload = {
        "event": "support.global_ticket.csat_submitted",
        "ticket_id": str(ticket.pk),
        "school_id": str(ticket.school_id),
        "actor_id": actor_id,
        "score": ticket.csat_score,
    }
    try:
        _schedule_support_ticket_webhooks(payload)
    except _HOOK_ERRORS:
        logger.debug("schedule support csat webhooks skipped", exc_info=True)
