"""Shared tenant support hub context (merged into Help center)."""

from __future__ import annotations

from typing import Any

from django.db import DatabaseError
from django.urls import reverse

from apps.platform_runtime.helpers import get_effective_support_contact_settings

_SUPPORT_TICKET_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


def build_tenant_support_hub_context(request) -> dict[str, Any]:
    """Tickets, school contact, and escalation data formerly on portal:support_help_hub."""
    school = getattr(request, "school", None)
    support_contact = get_effective_support_contact_settings(
        request=request, school=school
    )
    my_tickets: list = []
    if school is not None:
        try:
            from apps.siteconfig.models_feature_controls import GlobalSupportTicket

            my_tickets = list(
                GlobalSupportTicket.objects.filter(school=school, user=request.user)
                .order_by("-created_at")[:25]
            )
        except _SUPPORT_TICKET_SOFT_FAILURES:
            my_tickets = []

    contact_open_count = 0
    try:
        from apps.communication.models import ContactRequest

        if school is not None:
            open_statuses = (
                ContactRequest.Status.OPEN,
                ContactRequest.Status.TRIAGED,
                ContactRequest.Status.ASSIGNED,
                ContactRequest.Status.IN_PROGRESS,
            )
            contact_open_count = ContactRequest.objects.filter(
                parent=request.user, school=school, status__in=open_statuses
            ).count()
    except _SUPPORT_TICKET_SOFT_FAILURES:
        contact_open_count = 0

    role = (getattr(request.user, "role", "") or "").upper()
    is_parent = role == "PARENT"
    staff_contact_url = reverse("portal:staff_contact_request_list")
    show_staff_inbox = bool(
        getattr(request.user, "is_staff", False)
        or getattr(request.user, "is_superuser", False)
    )

    return {
        "school": school,
        "support_contact": support_contact,
        "my_tickets": my_tickets,
        "contact_open_count": contact_open_count,
        "is_parent": is_parent,
        "show_staff_inbox": show_staff_inbox,
        "staff_contact_url": staff_contact_url,
        "kb_home_url": reverse("kb:kb_home"),
        "faq_url": reverse("kb:faq_list"),
        "support_form_url": reverse("portal:support_request"),
        "parent_contact_url": reverse("portal:parent_contact_school"),
    }
