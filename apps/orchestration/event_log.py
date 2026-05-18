"""Event-sourced step log helpers for orchestration runs (Move 2)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from apps.orchestration.models import OrchestrationRun, OrchestrationStepEvent


@transaction.atomic
def emit(
    run: OrchestrationRun,
    *,
    event_type: str,
    step_name: str = "",
    payload: dict | None = None,
    error_message: str = "",
    duration_ms: int | None = None,
) -> OrchestrationStepEvent:
    """Append an immutable event to a run's log.

    `sequence_number` is assigned in-transaction so concurrent writers don't collide.
    Caller is responsible for ensuring `event_type` is one of OrchestrationStepEvent.EventType.
    """

    last = OrchestrationStepEvent.objects.select_for_update().filter(run=run).aggregate(
        m=Max("sequence_number")
    )["m"] or 0
    return OrchestrationStepEvent.objects.create(
        run=run,
        sequence_number=last + 1,
        event_type=event_type,
        step_name=step_name[:120],
        payload=payload or {},
        error_message=error_message[:5000],
        duration_ms=duration_ms,
    )


def events_for(run: OrchestrationRun):
    """Return queryset of events for a run in chronological order."""

    return OrchestrationStepEvent.objects.filter(run=run).order_by("sequence_number")


def project_status(run: OrchestrationRun) -> dict:
    """Cheap projection summary for API responses (Move 2 dashboard surface)."""

    qs = events_for(run)
    last_evt = qs.last()
    step_runs = sum(1 for e in qs if e.event_type == OrchestrationStepEvent.EventType.STEP_SUCCEEDED)
    step_failures = sum(1 for e in qs if e.event_type == OrchestrationStepEvent.EventType.STEP_FAILED)
    retries = sum(1 for e in qs if e.event_type == OrchestrationStepEvent.EventType.RETRY_SCHEDULED)
    return {
        "run_id": run.pk,
        "status": run.status,
        "last_event": last_evt.event_type if last_evt else None,
        "step_succeeded": step_runs,
        "step_failed": step_failures,
        "retries_scheduled": retries,
        "event_count": qs.count(),
    }
