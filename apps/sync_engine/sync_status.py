"""Live, school-scoped edge-sync status for Sync Center.

The panel used to render ``EdgeSyncRun.latest_for`` only. That hid a queued
full-resync (and any in-progress cycle) behind the last FAILED row — the
screenshot bug: two later syncs queued cleanly while the badge still said
failed. This module composes the headline from real rows, in priority order:

1. unfinished ``EdgeSyncRun`` (box cycle currently executing)
2. unserved ``EdgeSyncDirective`` (cloud queued work the box has not collected)
3. newest finished run
4. idle

Counts and timestamps come from those rows. Nothing here invents progress.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

PHASE_RUNNING = "running"
PHASE_QUEUED = "queued"
PHASE_OK = "ok"
PHASE_FAILED = "failed"
PHASE_IDLE = "idle"

_RECENT_RUN_CAP = 8
_WORKFLOW_KEY = "siteconfig-edge-sync"
_CYCLE_STEPS = 2  # push then pull — never use row counts as the percent bar


def _in_progress_steps(run) -> tuple[int, int]:
    """Return (processed, expected) for a live cycle.

    Telemetry pulses 0/2 → 1/2 → 2/2. Row ``pushed``/``pulled`` counts are
    stats, not a completion ratio — a 40-row push must not paint 100% while
    pull is still running.
    """
    expected = _CYCLE_STEPS
    pulled = int(getattr(run, "pulled", 0) or 0)
    created = int(getattr(run, "created", 0) or 0)
    upserted = int(getattr(run, "upserted", 0) or 0)
    if pulled or created or upserted:
        return expected, expected
    msg = (getattr(run, "message", None) or "").strip()
    if msg and msg != "running":
        return 1, expected
    return 0, expected


def _iso(value) -> str:
    if value is None:
        return ""
    try:
        return value.isoformat()
    except Exception:  # noqa: BLE001 — status payload must never 500
        return str(value)


def serialize_run(run) -> dict[str, Any] | None:
    if run is None:
        return None
    in_progress = run.finished_at is None
    processed = int(run.pushed or 0) + int(run.pulled or 0)
    expected = processed if in_progress and processed > 0 else processed
    if in_progress and expected < 1:
        expected = 1
    return {
        "id": run.pk,
        "mode": run.mode,
        "ok": bool(run.ok),
        "pushed": int(run.pushed or 0),
        "pulled": int(run.pulled or 0),
        "conflicts": int(run.conflicts or 0),
        "created": int(run.created or 0),
        "upserted": int(run.upserted or 0),
        "message": run.message or "",
        "error": run.error or "",
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "created_at": _iso(run.created_at),
        "in_progress": in_progress,
        "processed": processed,
        "expected": expected,
    }


def record_observed_cycle(school, **kw):
    """Record a finished cycle observed on the CLOUD (inbound push / directive).

    The box writes ``EdgeSyncRun`` into its own database. The SaaS tenant page
    never sees those rows. When the box actually talks to the cloud, this
    helper stamps the same model on the tenant schema so "last sync" is the
    last real transfer, not an old failed click.
    """
    from django.utils import timezone

    from apps.sync_engine.models import EdgeSyncRun

    now = timezone.now()
    kw.setdefault("started_at", now)
    kw.setdefault("finished_at", now)
    kw.setdefault("mode", "live")
    return EdgeSyncRun.record(school, **kw)


def serialize_live_status(school) -> dict[str, Any]:
    """Return the JSON/template payload for one school's live sync state."""
    from django.conf import settings

    from apps.sync_engine.edge_scheduler import edge_sync_interval_seconds
    from apps.sync_engine.models import EdgeSyncDirective, EdgeSyncRun

    empty = {
        "phase": PHASE_IDLE,
        "headline": _("No sync has run yet."),
        "badge": _("Idle"),
        "edge_sync_enabled": bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)),
        "latest": None,
        "recent_runs": [],
        "pending_resync": None,
        "last_served_resync": None,
        "pending_conflicts": 0,
        "sync_interval_seconds": edge_sync_interval_seconds(),
        "pushed": 0,
        "pulled": 0,
        "conflicts": 0,
        "processed": 0,
        "expected": 0,
        "percent_complete": "0.00",
        "workflow_key": _WORKFLOW_KEY,
        "task_type": "EDGE_SYNC",
        "current_status": PHASE_IDLE,
        "latest_trace_log": "",
    }
    if school is None:
        return empty

    try:
        from apps.siteconfig.models import SyncConflict

        pending_conflicts = SyncConflict.objects.filter(
            school=school,
            status=SyncConflict.Status.PENDING,
        ).count()
    except Exception:  # noqa: BLE001 — conflicts panel is separate
        pending_conflicts = 0

    running = EdgeSyncRun.in_progress_for(school)
    latest = EdgeSyncRun.latest_for(school)
    recent = list(EdgeSyncRun.objects.filter(school=school)[:_RECENT_RUN_CAP])
    directives = EdgeSyncDirective.objects.filter(
        school=school, kind=EdgeSyncDirective.FULL_RESYNC
    )
    pending_resync = directives.filter(served_at__isnull=True).first()
    last_served = directives.filter(served_at__isnull=False).first()

    payload = dict(empty)
    payload["pending_conflicts"] = int(pending_conflicts or 0)
    payload["latest"] = serialize_run(latest)
    payload["recent_runs"] = [serialize_run(row) for row in recent]
    if pending_resync is not None:
        payload["pending_resync"] = {
            "id": pending_resync.pk,
            "requested_at": _iso(pending_resync.requested_at),
        }
    if last_served is not None:
        payload["last_served_resync"] = {
            "id": last_served.pk,
            "served_at": _iso(last_served.served_at),
        }

    display = running or latest
    if display is not None:
        serialized = serialize_run(display) or {}
        payload["pushed"] = serialized.get("pushed", 0)
        payload["pulled"] = serialized.get("pulled", 0)
        payload["conflicts"] = serialized.get("conflicts", 0)
        payload["processed"] = serialized.get("processed", 0)
        payload["expected"] = serialized.get("expected", 0)

    if running is not None:
        payload["phase"] = PHASE_RUNNING
        payload["badge"] = _("Sync running")
        payload["headline"] = running.message or _("Sync cycle in progress.")
        payload["current_status"] = "running"
        payload["latest_trace_log"] = running.message or running.error or ""
        processed, expected = _in_progress_steps(running)
        payload["processed"] = processed
        payload["expected"] = expected
        payload["percent_complete"] = _percent(processed, expected)
        return payload

    if pending_resync is not None:
        payload["phase"] = PHASE_QUEUED
        payload["badge"] = _("Sync queued")
        payload["headline"] = _(
            "Full resync queued — waiting for the box to connect."
        )
        payload["current_status"] = "running"
        payload["latest_trace_log"] = payload["headline"]
        # Queued work has not started transferring rows yet.
        payload["percent_complete"] = "0.00"
        payload["processed"] = 0
        payload["expected"] = 1
        return payload

    if latest is not None:
        if latest.ok:
            payload["phase"] = PHASE_OK
            payload["badge"] = _("Last sync OK")
            payload["headline"] = latest.message or _("Last sync completed.")
            payload["current_status"] = "succeeded"
            payload["percent_complete"] = "100.00"
        else:
            payload["phase"] = PHASE_FAILED
            payload["badge"] = _("Last sync failed")
            payload["headline"] = latest.error or latest.message or _(
                "Last sync finished with errors."
            )
            payload["current_status"] = "failed"
            payload["percent_complete"] = "0.00"
        payload["latest_trace_log"] = payload["headline"]
        if last_served is not None and _served_beats_run(last_served, latest):
            payload["phase"] = PHASE_OK
            payload["badge"] = _("Resync collected")
            payload["headline"] = _("Box collected the queued full resync.")
            payload["current_status"] = "succeeded"
            payload["latest_trace_log"] = payload["headline"]
        return payload

    if last_served is not None:
        payload["phase"] = PHASE_OK
        payload["badge"] = _("Resync collected")
        payload["headline"] = _("Box collected the queued full resync.")
        payload["current_status"] = "succeeded"
        payload["latest_trace_log"] = payload["headline"]
        return payload

    return payload


def _served_beats_run(directive, run) -> bool:
    served = getattr(directive, "served_at", None)
    if served is None or run is None:
        return False
    stamp = run.finished_at or run.created_at
    if stamp is None:
        return True
    return served > stamp


def _percent(processed: int, expected: int) -> str:
    from apps.platform_runtime.workflow_telemetry import compute_percent_complete

    return str(compute_percent_complete(int(processed or 0), int(expected or 0)))
