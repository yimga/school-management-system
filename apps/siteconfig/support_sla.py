"""
Support queue SLA — non-negotiable platform requirement.
Defines SLA targets (response / resolution hours by priority) and helpers to check breach.
Integrates with GlobalSupportTicket; used by control-plane support queue and runbooks.
"""
from django.conf import settings
from django.utils import timezone


# Default SLA hours (required; override via settings)
SUPPORT_SLA_RESPONSE_HOURS = getattr(
    settings,
    "SUPPORT_SLA_RESPONSE_HOURS",
    {"URGENT": 4, "HIGH": 8, "NORMAL": 24, "LOW": 48},
)
SUPPORT_SLA_RESOLUTION_HOURS = getattr(
    settings,
    "SUPPORT_SLA_RESOLUTION_HOURS",
    {"URGENT": 24, "HIGH": 48, "NORMAL": 72, "LOW": 120},
)


def get_sla_response_hours(priority: str) -> int:
    """Return required first-response time in hours for the given priority."""
    return SUPPORT_SLA_RESPONSE_HOURS.get(priority, SUPPORT_SLA_RESPONSE_HOURS.get("NORMAL", 24))


def get_sla_resolution_hours(priority: str) -> int:
    """Return required resolution time in hours for the given priority."""
    return SUPPORT_SLA_RESOLUTION_HOURS.get(priority, SUPPORT_SLA_RESOLUTION_HOURS.get("NORMAL", 72))


def ticket_response_breach(ticket) -> bool:
    """
    True if ticket has no first response within SLA.
    Assumes ticket has: created_at, priority, and optionally first_response_at (if added later).
    """
    from datetime import timedelta

    created = getattr(ticket, "created_at", None)
    if not created:
        return False
    first_response_at = getattr(ticket, "first_response_at", None)
    if first_response_at is not None:
        return False
    priority = getattr(ticket, "priority", "NORMAL") or "NORMAL"
    hours = get_sla_response_hours(priority)
    deadline = created + timedelta(hours=hours)
    return timezone.now() > deadline


def ticket_resolution_breach(ticket) -> bool:
    """
    True if ticket is not resolved/closed within SLA.
    Assumes ticket has: created_at, priority, status, updated_at.
    """
    from datetime import timedelta

    created = getattr(ticket, "created_at", None)
    if not created:
        return False
    status = getattr(ticket, "status", None)
    if status in ("RESOLVED", "CLOSED"):
        return False
    priority = getattr(ticket, "priority", "NORMAL") or "NORMAL"
    hours = get_sla_resolution_hours(priority)
    deadline = created + timedelta(hours=hours)
    return timezone.now() > deadline
