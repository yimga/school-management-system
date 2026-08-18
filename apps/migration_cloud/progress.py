"""Live progress tracking for the DAG view + SSE stream.

Emits ``MigrationProgressEvent`` rows and updates
``MigrationBundle.progress_snapshot`` as the pipeline + orchestrator walk
through stages. Callers (pipeline, orchestrator, asset pipeline) push
events via the lightweight :func:`emit` helper; the DAG view + SSE
endpoint subscribe to the bundle's event stream.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from .models import MigrationBundle, MigrationProgressEvent

logger = logging.getLogger(__name__)


_STANDARD_STAGES = (
    "PENDING", "INGESTING", "PROFILED", "CLASSIFIED",
    "MAPPED", "APPLYING", "APPLIED", "RECONCILED",
)


def _stage_graph(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Return an explicit graph shape for dashboard and API consumers."""
    nodes = [
        {
            "id": stage["name"],
            "label": stage["name"].replace("_", " ").title(),
            "status": stage["status"],
            "pct": stage["pct"],
            "rows": stage.get("rows", 0),
        }
        for stage in stages
    ]
    edges = [
        {
            "from": _STANDARD_STAGES[idx],
            "to": _STANDARD_STAGES[idx + 1],
            "label": "then",
        }
        for idx in range(len(_STANDARD_STAGES) - 1)
    ]
    return {"nodes": nodes, "edges": edges}


def emit(
    *,
    bundle_id: int,
    kind: str,
    stage: str = "",
    message: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    """Append a progress event. Never blocks the caller on a write failure."""
    try:
        MigrationProgressEvent.objects.create(
            bundle_id=bundle_id,
            kind=kind,
            stage=stage[:32],
            message=message[:2000],
            detail=detail or {},
        )
    except Exception:  # noqa: BLE001
        logger.debug("progress.emit failed", exc_info=True)
        return
    try:
        from apps.platform_runtime.workflow_telemetry import (
            TASK_MIGRATION_INGESTION,
            update_and_broadcast_progress,
        )

        detail = detail or {}
        processed = int(detail.get("rows") or detail.get("processed") or 0)
        expected = int(detail.get("expected") or detail.get("total") or 0)
        if expected <= 0 and stage in _STANDARD_STAGES:
            expected = len(_STANDARD_STAGES)
            processed = _STANDARD_STAGES.index(stage) + 1
        if expected <= 0:
            expected = 1
            processed = max(processed, 1 if kind == "stage_finished" else processed)
        bundle = (
            # tenant-isolation-allow: migration-progress-pk-lookup-for-school-scoped-telemetry-fanout
            MigrationBundle.objects.filter(pk=bundle_id).only("school_id").first()
        )
        school_id = str(getattr(bundle, "school_id", "") or "") if bundle else ""
        update_and_broadcast_progress(
            school_id=school_id,
            task_type=TASK_MIGRATION_INGESTION,
            workflow_key="migration_bundle_apply",
            processed=processed,
            expected=expected,
            log_message=message or kind or stage,
        )
    except Exception:  # noqa: BLE001
        logger.debug("progress.telemetry_broadcast failed", exc_info=True)


def refresh_snapshot(*, bundle: MigrationBundle, persist: bool = True) -> dict[str, Any]:
    """Recompute the live progress snapshot from the event stream.

    Snapshot shape::

        {
            "stages": [
                {"name": "INGESTING", "status": "done", "pct": 100,
                 "started": iso, "finished": iso, "rows": 1240},
                ...
            ],
            "updated_at": iso,
        }

    ``persist`` (default ``True``) writes the snapshot back to the bundle — what
    the worker (pipeline / orchestrator) and the operator DAG view want. A hot,
    read-only poller (the tenant progress endpoint, hit every ~2.5 s per viewer)
    passes ``persist=False`` to compute the live picture WITHOUT a DB write on a
    GET; the snapshot is still set in-memory so the caller sees a consistent
    object, and the worker keeps the stored copy fresh at each stage boundary.
    """
    events = list(
        MigrationProgressEvent.objects.filter(bundle=bundle).order_by("created_at")
    )
    by_stage: dict[str, dict[str, Any]] = {
        name: {"name": name, "status": "pending", "pct": 0, "rows": 0}
        for name in _STANDARD_STAGES
    }
    current_idx = _STANDARD_STAGES.index(bundle.status) if bundle.status in _STANDARD_STAGES else -1
    for i, name in enumerate(_STANDARD_STAGES):
        if i < current_idx:
            by_stage[name]["status"] = "done"
            by_stage[name]["pct"] = 100
        elif i == current_idx:
            by_stage[name]["status"] = "current"

    for ev in events:
        s = ev.stage or ev.detail.get("stage", "")
        if s not in by_stage:
            continue
        if ev.kind == "stage_started":
            by_stage[s].setdefault("started", ev.created_at.isoformat())
        elif ev.kind == "stage_finished":
            by_stage[s]["finished"] = ev.created_at.isoformat()
            by_stage[s]["status"] = "done"
            by_stage[s]["pct"] = 100
            if ev.detail.get("rows"):
                by_stage[s]["rows"] = int(ev.detail["rows"])
        elif ev.kind == "artifact_progress":
            pct = int(ev.detail.get("pct") or 0)
            if pct > by_stage[s]["pct"]:
                by_stage[s]["pct"] = pct
            if ev.detail.get("rows"):
                by_stage[s]["rows"] = max(by_stage[s].get("rows", 0), int(ev.detail["rows"]))

    stages = [by_stage[name] for name in _STANDARD_STAGES]
    snapshot = {
        "stages": stages,
        "graph": _stage_graph(stages),
        "updated_at": timezone.now().isoformat(),
        "current_status": bundle.status,
    }
    bundle.progress_snapshot = snapshot
    if persist:
        bundle.save(update_fields=["progress_snapshot", "updated_at"])
    return snapshot


def stream_events_since(*, bundle_id: int, after_id: int = 0):
    """Generator of (event_id, payload) tuples for SSE. Stateless — one query per call."""
    events = (
        MigrationProgressEvent.objects.filter(bundle_id=bundle_id, id__gt=after_id)
        .order_by("id")[:500]
    )
    for ev in events:
        yield ev.pk, {
            "id": ev.pk,
            "kind": ev.kind,
            "stage": ev.stage,
            "message": ev.message,
            "detail": ev.detail,
            "at": ev.created_at.isoformat(),
        }
