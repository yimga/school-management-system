"""Celery tasks driving orchestration (Move 2 of the strategic moves).

Replaces the synchronous management-command drive loop with a durable
Celery-backed runner. The mgmt command still exists for cron fallback, but
this is now the primary execution path.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(name="orchestration.process_due_runs", bind=True, max_retries=3)
def process_due_runs(self, limit: int = 50) -> int:
    """Process up to `limit` pending OrchestrationRuns.

    Wraps the existing `process_orchestration_runs` management command so we
    keep one execution code path. Re-raises on transient DB errors so Celery
    retries; other errors are logged and swallowed (the next tick will pick up
    where we left off).
    """

    try:
        call_command("process_orchestration_runs", "--limit", str(int(limit)))
    except Exception as exc:
        logger.warning("orchestration.process_due_runs failed: %s", exc)
        try:
            raise self.retry(exc=exc, countdown=30)
        except Exception:
            return 0
    return int(limit)


@shared_task(name="orchestration.trigger_runs_for_definition")
def trigger_runs_for_definition(code: str) -> int:
    """Materialize PENDING runs for a given ProcessDefinition.code.

    Useful for time-based triggers — e.g. "fire daily re-enrollment reminders".
    """

    try:
        call_command("trigger_orchestration_runs", "--code", code)
    except Exception as exc:
        logger.exception("trigger_runs_for_definition[%s] failed: %s", code, exc)
        return 0
    return 1


@shared_task(name="orchestration.aggregate_slos")
def aggregate_slos(window_minutes: int = 60) -> int:
    """Compute SLO metrics over the last `window_minutes` and store them.

    Cheap, idempotent: re-running for the same window updates the same row.
    """

    from apps.orchestration.slo_aggregator import aggregate_recent_window

    return aggregate_recent_window(window_minutes=window_minutes)
