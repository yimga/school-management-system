"""Celery tasks for the observability app."""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(name="observability.friction_digest_weekly")
def friction_digest_weekly() -> str:
    """Weekly internal friction digest over the last 7 days.

    Wraps the ``digest_friction`` management command (which carries the
    empathy-aware AI narrative) so it can be scheduled via Celery beat.
    Window is 168h so the weekly run covers the whole week, not just 24h.
    Never raises — a telemetry digest must never fail a beat.
    """
    try:
        call_command("digest_friction", hours=168)
    except Exception:  # noqa: BLE001 — a digest must never fail the beat
        logger.warning("friction_digest_weekly task failed", exc_info=True)
        return "error"
    return "ok"
