"""Celery tasks for customer success (Move 4)."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="customersuccess.run_auto_ticket_rules")
def run_auto_ticket_rules() -> dict:
    """Move 4 — drive AutoTicketRule evaluations. Returns count map per rule."""

    try:
        from apps.customersuccess.auto_ticket_runner import run_all_rules

        return run_all_rules()
    except Exception as exc:
        logger.exception("run_auto_ticket_rules failed: %s", exc)
        return {}
