"""
Side effects for observability models (cache coherency).
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.observability.models import PlatformIncident
from apps.observability.tenant_public_status import invalidate_platform_status_strip_cache


@receiver(post_save, sender=PlatformIncident)
@receiver(post_delete, sender=PlatformIncident)
def platform_incident_bust_tenant_status_strip_cache(**kwargs) -> None:
    """Tenant portal strip caches fleet + school-scoped rows; bump generation on any write."""
    invalidate_platform_status_strip_cache()
