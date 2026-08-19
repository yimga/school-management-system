"""Celery task wrapper for automatic edge<->cloud sync (the worker/beat path).

The in-process scheduler, the boot entrypoint, and the ``edge_autosync`` command all
call ``edge_scheduler.run_edge_sync_now`` directly. This module exposes the SAME
callable as a ``@shared_task`` so a box that DOES run a Celery worker+beat drives it
through the standard ``CELERY_BEAT_SCHEDULE`` entry — both paths run identical code.

Operator "Sync now" uses :func:`run_sync_cycle_for_school_task` so the HTTP worker
returns immediately and Sync Center can poll live percent on the same tab.
"""
from __future__ import annotations

import logging

try:  # celery is in requirements.txt; the guard keeps import-time safe without it
    from celery import shared_task
except ImportError:  # pragma: no cover - celery is always installed in this project
    shared_task = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def run_edge_sync_cycle() -> dict:
    """Plain (broker-free) entry the beat task and any caller can invoke.

    Deliberately NOT forced. Beat is a timer, not an intent — letting it bypass the
    adaptive cadence would reintroduce the fixed-interval behaviour the cadence exists to
    replace, and would keep building bundles at full rate while the box is offline. The
    beat entry ticks fast (see ``CELERY_BEAT_SCHEDULE["edge-sync-cycle"]``) and the
    cadence decides which ticks become real cycles.
    """
    from apps.sync_engine.edge_scheduler import run_edge_sync_now

    return run_edge_sync_now(mode="live", trigger="celery-beat")


def run_sync_cycle_for_school(
    school_id: int, mode: str = "live", run_id=None
) -> dict:
    """Run one cycle for a school, reusing the in-progress row the HTTP view opened."""
    from apps.schools.models import School
    from apps.sync_engine.models import EdgeSyncRun
    from apps.sync_engine.sync_runner import run_sync_cycle

    school = School.objects.filter(pk=school_id).first()
    if school is None:
        if run_id is not None:
            from django.utils import timezone as _tz

            EdgeSyncRun.objects.filter(
                pk=run_id,
                school_id=school_id,
                finished_at__isnull=True,
            ).update(
                ok=False,
                error="school_not_found",
                message="school_not_found",
                finished_at=_tz.now(),
            )
        return {"ok": False, "error": "school_not_found", "enabled": False}
    run_row = None
    if run_id is not None:
        run_row = EdgeSyncRun.objects.filter(pk=run_id, school_id=school_id).first()
        if run_row is None:
            # Do not begin() a second cycle — the HTTP worker already opened a row
            # that may not be visible yet (commit race). Caller retries.
            return {
                "ok": False,
                "error": "run_not_found",
                "enabled": True,
                "mode": mode,
            }
    result = run_sync_cycle(school, mode=mode, run_row=run_row)
    # Fold the operator's own cycle into the adaptive cadence, exactly as an automatic one
    # is. Without this the "Sync now" button is invisible to the scheduler: a click that
    # moved a hundred rows would leave the box STEADY (or still counting failures from an
    # outage that has plainly just ended), so the follow-up changes the operator is about
    # to make would crawl. A dry run is excluded — it writes nothing in either direction
    # and so proves no throughput and clears no real backoff.
    if mode == "live":
        try:
            from apps.sync_engine import cadence

            cadence.record_cycle(result)
        except Exception:  # noqa: BLE001 — cadence is an optimisation, never the request
            logger.debug("cadence record after operator sync failed", exc_info=True)
    return result


if shared_task is not None:

    @shared_task(name="sync_engine.edge_sync_cycle")
    def edge_sync_cycle_task() -> dict:
        return run_edge_sync_cycle()

    @shared_task(bind=True, name="sync_engine.run_sync_cycle_for_school", max_retries=5)
    def run_sync_cycle_for_school_task(
        self, school_id: int, mode: str = "live", run_id=None
    ) -> dict:
        from celery.exceptions import Retry

        from apps.schools.celery_tasks import _run_with_tenant_context

        def _run() -> dict:
            result = run_sync_cycle_for_school(school_id, mode=mode, run_id=run_id)
            if result.get("error") == "run_not_found":
                raise self.retry(countdown=1)
            return result

        try:
            return _run_with_tenant_context(
                school_id=str(school_id), runnable=_run
            ) or {}
        except Retry:
            raise
        except Exception as exc:  # noqa: BLE001 — never leave an open run hanging
            logger.warning(
                "sync_engine.run_sync_cycle_for_school tenant_context_failed school=%s err=%s",
                school_id,
                type(exc).__name__,
            )
            return _run()
else:  # pragma: no cover - celery is always installed in this project

    def run_sync_cycle_for_school_task(  # type: ignore[misc]
        school_id: int, mode: str = "live", run_id=None
    ) -> dict:
        return run_sync_cycle_for_school(school_id, mode=mode, run_id=run_id)
