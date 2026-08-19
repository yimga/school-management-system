"""Celery task wrapper for automatic edge<->cloud sync (the worker/beat path).

The in-process scheduler, the boot entrypoint, and the ``edge_autosync`` command all
call ``edge_scheduler.run_edge_sync_now`` directly. This module exposes the SAME
callable as a ``@shared_task`` so a box that DOES run a Celery worker+beat drives it
through the standard ``CELERY_BEAT_SCHEDULE`` entry — both paths run identical code.
"""
from __future__ import annotations

try:  # celery is in requirements.txt; the guard keeps import-time safe without it
    from celery import shared_task
except ImportError:  # pragma: no cover - celery is always installed in this project
    shared_task = None  # type: ignore[assignment]


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


if shared_task is not None:

    @shared_task(name="sync_engine.edge_sync_cycle")
    def edge_sync_cycle_task() -> dict:
        return run_edge_sync_cycle()
