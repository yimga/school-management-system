"""
Context processors for portal app.
"""
from django.db import DatabaseError, connection
from django.db.models import Q
from django.utils import timezone

from .models import Announcement


def announcements(request):
    """
    Context processor to pass active announcements to all templates.
    """
    if connection.in_atomic_block and connection.needs_rollback:
        return {"announcements": []}

    now = timezone.now()
    try:
        active_announcements = list(
            Announcement.objects.filter(is_active=True)
            .filter(
                Q(start_date__isnull=True) | Q(start_date__lte=now),
                Q(end_date__isnull=True) | Q(end_date__gte=now),
            )
            .values("id", "title", "message", "banner_type")
        )
    except DatabaseError:
        return {"announcements": []}

    return {"announcements": active_announcements}
