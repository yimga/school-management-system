"""Signals for FleetGovernedChange — audit events on create."""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.platform_runtime.models import FleetGovernedChange

logger = logging.getLogger(__name__)


@receiver(post_save, sender=FleetGovernedChange)
def fleet_governed_change_created_emit(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "fleet_governed_change_created",
            {
                "change_id": instance.pk,
                "change_type": instance.change_type,
                "status": instance.status,
                "created_by_id": instance.created_by_id,
                "title": (instance.title or "")[:200],
            },
        )
    except Exception:
        logger.debug("fleet_governed_change_created_emit failed", exc_info=True)
