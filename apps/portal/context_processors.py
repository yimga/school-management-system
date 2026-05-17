"""
Context processors for portal app.
"""

from django.db import DatabaseError, connection, transaction
from django.db.transaction import TransactionManagementError
from django.db.models import Q
from django.utils import timezone

from .models import Announcement


def platform_status_strip(request):
    """
    Public-safe active incident summary for tenant portal shells (cached ~60s).
    """
    try:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return {"platform_status_strip": {"show": False}}
        school = getattr(request, "school", None)
        school_id = getattr(school, "pk", None) if school is not None else None
        from apps.observability.tenant_public_status import (
            compute_platform_status_strip_bundle,
        )

        return {
            "platform_status_strip": compute_platform_status_strip_bundle(school_id)
        }
    except (DatabaseError, TransactionManagementError):
        _reset_db_state()
        return {"platform_status_strip": {"show": False}}


def _reset_db_state() -> None:
    """Reset a broken transaction after a handled DB error."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        else:
            connection.rollback()
    except (DatabaseError, TransactionManagementError):
        pass


def announcements(request):
    """
    Context processor to pass active announcements to all templates.
    """
    try:
        if connection.needs_rollback:
            _reset_db_state()
            return {"announcements": []}
        now = timezone.now()
        active_announcements = (
            # tenant-isolation-allow: context-scoped-via-request-school-membership
            Announcement.objects.filter(is_active=True)
            .filter(
                Q(start_date__isnull=True) | Q(start_date__lte=now),
                Q(end_date__isnull=True) | Q(end_date__gte=now),
            )
            .values("id", "title", "message", "banner_type")
        )
        return {"announcements": list(active_announcements)}
    except (DatabaseError, TransactionManagementError):
        _reset_db_state()
        return {"announcements": []}
