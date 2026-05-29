"""
v4.00.37 — Quick-create JSON endpoint backing the universal "Report issue" chip.

Accepts a tiny payload (subject + message + template_key + context_json) from
the floating chip on every tenant shell. Mirrors the existing support_request
flow but returns JSON so the chip stays in-place and the user gets an instant
acknowledgement plus a deep link to the ticket detail page.

Auto-context fields captured:
- current URL path
- role label
- browser user-agent / platform / viewport / language
- captured_at timestamp

The context is stored on ticket.metadata under the "client_context" key so
operators can see exactly where the user was when they filed the ticket.
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.communication.models import Message

from .views_support import SUPPORT_TICKET_SOFT_FAILURES, _pick_support_owner


TEMPLATE_LABELS = {
    "login": "Can't log in",
    "grade": "Grade or mark issue",
    "bug": "Something broken",
    "feature": "Feature request",
    "billing": "Billing question",
    "other": "Other",
}


def _parse_context(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Cap each value at 480 chars; reject anything not stringifiable.
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str) or len(key) > 64:
            continue
        if value is None:
            continue
        try:
            text = str(value)
        except Exception:  # noqa: BLE001 — defensive against weird inputs
            continue
        cleaned[key] = text[:480]
    return cleaned


@login_required
@require_POST
def support_quick_create(request: HttpRequest) -> JsonResponse:
    """Accept a minimal multipart payload + JSON context and create a ticket."""
    subject = (request.POST.get("subject") or "").strip()[:200]
    message = (request.POST.get("message") or "").strip()
    template_key = (request.POST.get("template_key") or "").strip()[:32]
    context = _parse_context(request.POST.get("context_json") or "")

    if not subject or not message:
        return JsonResponse(
            {"error": "missing_fields", "detail": "subject and message are required"},
            status=400,
        )

    school = getattr(request, "school", None)
    if school is None:
        return JsonResponse(
            {"error": "no_school_context"},
            status=400,
        )

    template_label = TEMPLATE_LABELS.get(template_key, "")
    full_subject_parts = ["[Support]"]
    if template_label:
        full_subject_parts.append(f"[{template_label}]")
    full_subject_parts.append(subject)
    full_subject = " ".join(full_subject_parts)[:255]

    captured_path = context.get("url") or request.path
    role_label = context.get("role_label") or getattr(request.user, "role", "") or ""
    body_lines = [
        f"From: {request.user.get_full_name() or request.user.username}",
        f"Role: {role_label or request.user.role}",
        f"Email: {request.user.email or 'N/A'}",
        f"Path: {captured_path}",
        "",
        message,
    ]
    body = "\n".join(body_lines)

    ticket = None
    try:
        from apps.portal.runtime_helpers import get_policy_for_request
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        policy = get_policy_for_request(request)
        plan_slug = (policy.get("plan_slug") or "").strip().lower()
        country_code = (policy.get("country_code") or "")[:2]
        priority = GlobalSupportTicket.Priority.NORMAL
        if plan_slug in ("powerhouse", "enterprise", "pro"):
            priority = GlobalSupportTicket.Priority.HIGH

        metadata = {
            "country_code": country_code,
            "plan_slug": plan_slug,
            "category": "SUPPORT",
            "submission_surface": "quick_create_chip",
            "template_key": template_key or None,
            "client_context": context,
        }
        ticket = GlobalSupportTicket.objects.create(
            school=school,
            user=request.user,
            subject=full_subject,
            body=body,
            priority=priority,
            status=GlobalSupportTicket.Status.OPEN,
            metadata=metadata,
        )
    except SUPPORT_TICKET_SOFT_FAILURES:
        ticket = None

    if ticket is None:
        return JsonResponse(
            {"error": "ticket_persist_failed"},
            status=500,
        )

    # v4.00.42 — attachment persistence. Accepts up to 5 files, 10 MB each.
    attachment_ids: list[str] = []
    try:
        from apps.siteconfig.models_feature_controls import (
            GlobalSupportTicketAttachment,
        )

        uploaded = request.FILES.getlist("attachments") if request.FILES else []
        for upload in uploaded[:5]:
            try:
                if upload.size and upload.size > 10 * 1024 * 1024:
                    continue
                row = GlobalSupportTicketAttachment.objects.create(
                    ticket=ticket,
                    uploader=request.user,
                    file=upload,
                    filename=(upload.name or "attachment")[:255],
                    content_type=(getattr(upload, "content_type", "") or "")[:120],
                    byte_size=int(upload.size or 0),
                    source=GlobalSupportTicketAttachment.Source.QUICK_CREATE,
                    visible_to_submitter=True,
                )
                attachment_ids.append(str(row.pk))
            except SUPPORT_TICKET_SOFT_FAILURES:
                continue
    except SUPPORT_TICKET_SOFT_FAILURES:
        attachment_ids = []

    recipient = _pick_support_owner()
    msg = None
    if recipient:
        try:
            from apps.communication.comms_locale import locale_target_for_user

            msg = Message.objects.create(
                sender=request.user,
                recipient=recipient,
                subject=full_subject,
                body=body,
                locale_target=locale_target_for_user(recipient),
            )
        except (DatabaseError, ImportError, AttributeError):
            msg = None

    if msg is not None:
        try:
            md = dict(ticket.metadata or {})
            md["communication_message_id"] = msg.pk
            type(ticket).objects.filter(pk=ticket.pk).update(metadata=md)
        except SUPPORT_TICKET_SOFT_FAILURES:
            pass

    tid = str(ticket.pk)
    rid = recipient.pk if recipient else None

    def _created_hooks() -> None:
        try:
            from apps.siteconfig.support_ticket_hooks import (
                run_support_ticket_created_hooks,
            )

            run_support_ticket_created_hooks(tid, primary_recipient_id=rid)
        except SUPPORT_TICKET_SOFT_FAILURES:
            pass
        # v4.00.43 — AI triage runs after commit so DB row is durable. Soft-fails.
        try:
            from apps.siteconfig.support_ai_triage import run_ai_triage

            run_ai_triage(ticket, request=None)
        except SUPPORT_TICKET_SOFT_FAILURES:
            pass

    transaction.on_commit(_created_hooks)

    try:
        ticket_url = reverse("portal:support_ticket_detail", args=[ticket.pk])
    except Exception:  # noqa: BLE001 — best-effort URL
        ticket_url = ""

    return JsonResponse(
        {
            "ok": True,
            "ticket_id": str(ticket.pk),
            "ticket_url": ticket_url,
            "priority": ticket.priority,
            "status": ticket.status,
            "attachment_ids": attachment_ids,
        },
        status=201,
    )


@login_required
def kb_search_inline(request: HttpRequest) -> JsonResponse:
    """Lightweight KB search backing the quick-create chip's deflection hits.

    Returns up to 3 ranked KB articles for the typed query so the user can
    self-serve before submitting. Falls back to icontains when the ranker
    is unavailable.
    """
    query = (request.GET.get("q") or "").strip()[:120]
    if not query or len(query) < 4:
        return JsonResponse({"results": []})

    results: list[dict[str, str]] = []
    try:
        from apps.portal.views_kb import _published_kb_for_request

        base_qs = _published_kb_for_request(request)
        try:
            from apps.portal.kb_search import search_kb_articles

            ranked = search_kb_articles(base_qs, query, limit=3) or []
        except Exception:  # noqa: BLE001 — fall back to substring match
            ranked = []
        if ranked:
            articles = [a for a, _score in ranked]
        else:
            from apps.siteconfig.list_search import apply_bounded_icontains

            articles = list(
                apply_bounded_icontains(
                    base_qs, query, "title", "summary", "content", "tags"
                )[:3]
            )
        for article in articles:
            slug = getattr(article, "slug", None) or ""
            url = ""
            try:
                from django.urls import reverse as _reverse

                url = _reverse("kb:kb_article", args=[slug]) if slug else ""
            except Exception:  # noqa: BLE001 — best-effort link
                url = ""
            results.append(
                {
                    "title": (getattr(article, "title", "") or "")[:140],
                    "summary": (getattr(article, "summary", "") or "")[:200],
                    "url": url,
                }
            )
    except Exception:  # noqa: BLE001 — KB index optional
        results = []

    return JsonResponse({"results": results})
