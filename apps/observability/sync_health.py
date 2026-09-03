"""Cross-rail sync health (9.8 sync-observability wave, 2026-07-02).

The platform has FOUR offline/sync rails whose failures land in four
different stores with wildly different visibility:

  * delta-sync   -> ``SyncConflict`` rows (operator SLO dashboard sees these)
  * SODP queue   -> ``OfflineAction`` rows (tenant portal only — no operator
                    rollup existed before this module)
  * WAL/oplog    -> Redis review streams ``rmc.wal.deadletter.<hash>`` and
                    ``rmc.wal.conflict.<hash>`` (write-only before this module:
                    no reader, UI, metric, or alert anywhere in the codebase)
  * edge rows    -> ``sync_engine.SyncDeadLetter`` rows: individual records the
                    edge apply path keeps refusing. Added 2026-08-31, and it is
                    the rail that could NOT reach this module before: a refused
                    row raises no ``SyncConflict`` (nobody is being asked to
                    choose), so it was counted into the per-CYCLE
                    ``EdgeSyncRun.skipped`` and discarded. No number this
                    collector read could grow when a box stalled, so no
                    incident could open — and one box re-refused the same 39
                    rows on all 687 cycles of a day in total silence.

This module is the single cross-rail collector: one call returns per-rail
backlog/conflict/dead-letter counts + lag, emits gauges through the
observability metrics bridge, and feeds both the operator console
(``/portal/super/sync-health/``) and the periodic backlog monitor that
auto-opens/auto-resolves a ``PlatformIncident`` when a rail breaches its
settings-driven threshold.
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_WAL_REVIEW_PREFIXES = {
    "deadletter": "rmc.wal.deadletter.",
    "conflict": "rmc.wal.conflict.",
}
_WAL_BACKLOG_SIDE_PREFIXES = (
    "rmc.wal.dedupe.",
    "rmc.wal.attempts.",
    "rmc.wal.deadletter.",
    "rmc.wal.conflict.",
    "rmc.wal.lock.",
)
_SAMPLE_FIELD_MAX_CHARS = 200
_MAX_REVIEW_STREAMS = 200


def _get_redis_client():
    """Same defensive acquisition as wal_stream.tasks — never raises."""
    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        return None
    redis_url = getattr(settings, "REDIS_URL", "") or getattr(settings, "CELERY_BROKER_URL", "")
    if not redis_url:
        return None
    try:
        return redis.Redis.from_url(redis_url)
    except Exception:  # noqa: BLE001 — health collection must never crash a caller
        return None


def _age_seconds(dt) -> int | None:
    if dt is None:
        return None
    return max(0, int((timezone.now() - dt).total_seconds()))


def _collect_sodp() -> dict[str, Any]:
    from apps.platform_runtime.models import OfflineAction

    counts = {status: 0 for status in ("queued", "syncing", "failed", "conflict")}
    rows = OfflineAction.objects.filter(  # tenant-isolation-allow: platform-wide-sync-health-rollup-operator-observability
        status__in=list(counts)
    ).values_list("status")
    for (status_value,) in rows:
        counts[status_value] = counts.get(status_value, 0) + 1
    oldest_queued = (
        OfflineAction.objects.filter(status=OfflineAction.Status.QUEUED)  # tenant-isolation-allow: platform-wide-sync-health-rollup-operator-observability
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    oldest_conflict = (
        OfflineAction.objects.filter(status=OfflineAction.Status.CONFLICT)  # tenant-isolation-allow: platform-wide-sync-health-rollup-operator-observability
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return {
        **counts,
        "oldest_queued_age_seconds": _age_seconds(oldest_queued),
        "oldest_conflict_age_seconds": _age_seconds(oldest_conflict),
    }


def _collect_delta() -> dict[str, Any]:
    from apps.siteconfig.models_platform_catalog import SyncConflict

    pending_qs = SyncConflict.objects.filter(status=SyncConflict.Status.PENDING)  # tenant-isolation-allow: platform-wide-sync-health-rollup-operator-observability
    oldest_pending = (
        pending_qs.order_by("created_at").values_list("created_at", flat=True).first()
    )
    return {
        "pending": pending_qs.count(),
        "oldest_pending_age_seconds": _age_seconds(oldest_pending),
    }


def _collect_edge() -> dict[str, Any]:
    """The EDGE row rail: individual rows the sync apply path keeps refusing.

    THE RAIL THAT COULD NOT REACH THIS MODULE. ``_collect_delta`` above reads pending
    ``SyncConflict`` rows, and a refused row is not a conflict — nobody is being asked to
    choose, so no SyncConflict is ever created for it. The refusals went into
    ``EdgeSyncRun.skipped``, a per-CYCLE counter that this collector never read, so a box
    that refused the same rows on every cycle of a day could not open an incident: there
    was no number here for :func:`evaluate_backlog_incidents` to threshold. A stalled box
    stayed silent by construction, and one did — 39 teacher rows, 687 cycles, 26,598
    "not applied", no alarm, several days to diagnose by hand.

    ``EdgeSyncRun.skipped`` is deliberately NOT what this reads. It is a sum of ATTEMPTS:
    it grows on a healthy busy box, it grows 687× faster than the problem does, and it
    cannot answer how many rows are actually stuck. :class:`~apps.sync_engine.models.SyncDeadLetter`
    is one record per stuck ROW, which is the quantity a threshold can mean something
    about.

    ``oldest_stuck_age_seconds`` is the field that matters most, and it is here rather
    than only a depth because DEPTH ALONE TOLERATES A PERMANENT BACKLOG. 39 stuck rows is
    39 whether they appeared a minute ago (a parent arriving next cycle — the normal,
    self-healing case) or three weeks ago (wedged). Only the age separates them.

    Never raises: a deployment whose sync tables are not migrated yet gets a zeroed rail
    rather than a collector that takes the whole cross-rail snapshot down with it.
    """
    zero = {
        "available": False,
        "stuck_rows": 0,
        "attempts_total": 0,
        "oldest_stuck_age_seconds": None,
        "schools_affected": 0,
    }
    try:
        from apps.sync_engine.models import dead_letter_summary, open_dead_letters

        summary = dead_letter_summary()  # school=None → every tenant, the operator rollup
        schools = (
            open_dead_letters()  # tenant-isolation-allow: platform-wide-sync-health-rollup-operator-observability
            .values_list("school_id", flat=True)
            .distinct()
            .count()
        )
        return {
            "available": True,
            "stuck_rows": summary["count"],
            "attempts_total": summary["attempts_total"],
            "oldest_stuck_age_seconds": summary["oldest_age_seconds"],
            "schools_affected": schools,
        }
    except Exception as exc:  # noqa: BLE001 — health collection must never crash a caller
        logger.warning("sync_health.edge_collect_failed err=%s", exc)
        return zero


def _collect_wal(client) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": client is not None,
        "backlog_streams": 0,
        "backlog_depth": 0,
        "deadletter_streams": 0,
        "deadletter_depth": 0,
        "conflict_streams": 0,
        "conflict_depth": 0,
    }
    if client is None:
        return result
    try:
        for raw_key in client.scan_iter(match="rmc.wal.*", count=200):
            key = raw_key.decode("utf-8") if isinstance(raw_key, (bytes, bytearray)) else raw_key
            if key.startswith(("rmc.wal.dedupe.", "rmc.wal.attempts.", "rmc.wal.lock.")):
                continue  # non-stream sidecars (XLEN raises on the HASH/SET types)
            try:
                depth = int(client.xlen(key))
            except Exception:  # noqa: BLE001 — foreign key types must not abort the sweep
                continue
            if key.startswith("rmc.wal.deadletter."):
                result["deadletter_streams"] += 1
                result["deadletter_depth"] += depth
            elif key.startswith("rmc.wal.conflict."):
                result["conflict_streams"] += 1
                result["conflict_depth"] += depth
            else:
                if depth:
                    result["backlog_streams"] += 1
                    result["backlog_depth"] += depth
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync_health.wal_scan_failed err=%s", exc)
        result["available"] = False
    return result


def collect_sync_health(redis_client=...) -> dict[str, Any]:
    """One cross-rail snapshot. Emits gauges through the metrics bridge.

    ``redis_client`` is injectable for tests; the default acquires the real
    client (or degrades to ``available: False`` when Redis is absent).
    """
    from apps.observability.metrics import emit_gauge

    client = _get_redis_client() if redis_client is ... else redis_client
    snapshot = {
        "collected_at": timezone.now().isoformat(),
        "sodp": _collect_sodp(),
        "delta": _collect_delta(),
        "edge": _collect_edge(),
        "wal": _collect_wal(client),
    }
    emit_gauge("rmc.sync.sodp.queued", snapshot["sodp"]["queued"])
    emit_gauge("rmc.sync.sodp.failed", snapshot["sodp"]["failed"])
    emit_gauge("rmc.sync.sodp.conflict", snapshot["sodp"]["conflict"])
    emit_gauge("rmc.sync.delta.pending", snapshot["delta"]["pending"])
    # Both, and named apart. The depth is what an operator eyeballs; the AGE is what the
    # incident evaluator thresholds on, and a dashboard carrying only the depth would
    # re-create the blind spot this rail exists to close.
    emit_gauge("rmc.sync.edge.stuck_rows", snapshot["edge"]["stuck_rows"])
    emit_gauge(
        "rmc.sync.edge.oldest_stuck_age_seconds",
        snapshot["edge"]["oldest_stuck_age_seconds"] or 0,
    )
    emit_gauge("rmc.sync.wal.backlog_depth", snapshot["wal"]["backlog_depth"])
    emit_gauge("rmc.sync.wal.deadletter_depth", snapshot["wal"]["deadletter_depth"])
    emit_gauge("rmc.sync.wal.conflict_depth", snapshot["wal"]["conflict_depth"])
    return snapshot


def peek_wal_review_streams(kind: str, *, limit_per_stream: int = 3, redis_client=...) -> list[dict[str, Any]]:
    """First-ever reader for the WAL review streams (dead-letter / conflict).

    Returns per-stream samples for the operator console. Sample fields are
    truncated and reduced to the review-relevant keys (``error``, ``domain``)
    — full envelopes stay in Redis; this surface is for triage, not replay.
    """
    prefix = _WAL_REVIEW_PREFIXES.get(kind)
    if prefix is None:
        raise ValueError(f"unknown review-stream kind: {kind!r}")
    client = _get_redis_client() if redis_client is ... else redis_client
    if client is None:
        return []
    streams: list[dict[str, Any]] = []
    try:
        for raw_key in client.scan_iter(match=f"{prefix}*", count=200):
            key = raw_key.decode("utf-8") if isinstance(raw_key, (bytes, bytearray)) else raw_key
            try:
                depth = int(client.xlen(key))
            except Exception:  # noqa: BLE001
                continue
            samples = []
            try:
                for entry_id, fields in client.xrevrange(key, count=limit_per_stream):
                    entry_id = entry_id.decode() if isinstance(entry_id, (bytes, bytearray)) else entry_id
                    cleaned = {}
                    for fk, fv in (fields or {}).items():
                        fk = fk.decode() if isinstance(fk, (bytes, bytearray)) else fk
                        if fk not in ("error", "domain"):
                            continue
                        fv = fv.decode("utf-8", "replace") if isinstance(fv, (bytes, bytearray)) else str(fv)
                        cleaned[fk] = fv[:_SAMPLE_FIELD_MAX_CHARS]
                    samples.append({"id": entry_id, "fields": cleaned})
            except Exception:  # noqa: BLE001
                pass
            streams.append({
                "stream": key,
                "tenant_hash": key.rsplit(".", 1)[-1],
                "depth": depth,
                "samples": samples,
            })
            if len(streams) >= _MAX_REVIEW_STREAMS:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync_health.review_peek_failed kind=%s err=%s", kind, exc)
    streams.sort(key=lambda s: -s["depth"])
    return streams


def evaluate_backlog_incidents(snapshot: dict[str, Any] | None = None, *, redis_client=...) -> dict[str, Any]:
    """Threshold check per rail → auto-open/auto-resolve a PlatformIncident.

    Uses the idempotent incident services (keyed ``sync_backlog_<rail>``), so a
    breach that persists updates one incident and recovery resolves it — the
    operator SLO dashboard, cockpit banner, and incident console all see it.

    TWO RAILS PER QUESTION FOR THE EDGE ROWS, and the second one is the point.
    ``edge_stuck_rows`` is an ordinary depth threshold. ``edge_stuck_age`` thresholds on
    the AGE OF THE OLDEST stuck row, because depth alone tolerates a permanent backlog
    forever: a box sitting at a constant 39 refused rows never crosses a depth line it has
    not already crossed, so a stall that never drains looks exactly like a stall that is
    about to. Age is the only signal that separates them, and its absence is precisely why
    a box spent a whole day re-refusing the same 39 rows without opening anything.
    """
    from apps.observability.incident_services import (
        resolve_platform_incident,
        upsert_platform_incident,
    )
    from apps.observability.models import PlatformIncident

    if snapshot is None:
        snapshot = collect_sync_health(redis_client=redis_client)
    edge = snapshot.get("edge") or {}
    # (measured value, ceiling, unit label). The unit is carried rather than assumed
    # because one of these rails is measured in SECONDS and a summary reading
    # "edge_stuck_age at 50400 (max 21600)" with no unit is a number an operator has to
    # decode before they can act on it.
    thresholds = {
        "sodp_conflict": (
            snapshot["sodp"]["conflict"],
            int(getattr(settings, "RMC_SYNC_SODP_CONFLICT_MAX", 25)),
            "rows",
        ),
        "delta_pending": (
            snapshot["delta"]["pending"],
            int(getattr(settings, "SYNC_CONFLICT_PENDING_SLO_MAX", 10)),
            "rows",
        ),
        "wal_deadletter": (
            snapshot["wal"]["deadletter_depth"],
            int(getattr(settings, "RMC_SYNC_WAL_DEADLETTER_MAX", 10)),
            "entries",
        ),
        # DISTINCT stuck rows, never EdgeSyncRun.skipped — see _collect_edge.
        "edge_stuck_rows": (
            int(edge.get("stuck_rows") or 0),
            int(getattr(settings, "RMC_SYNC_EDGE_STUCK_ROWS_MAX", 25)),
            "rows",
        ),
        # The one that would have caught the real incident. Default 6h: long enough that
        # an absent parent arriving on a later pull never trips it, short enough that a
        # box wedged since this morning is somebody's problem before it is a whole day's.
        "edge_stuck_age": (
            int(edge.get("oldest_stuck_age_seconds") or 0),
            int(getattr(settings, "RMC_SYNC_EDGE_STUCK_AGE_MAX_SECONDS", 6 * 3600)),  # magic-number-allow: six hours, expressed as hours x seconds-per-hour
            "seconds",
        ),
    }
    outcome: dict[str, Any] = {"opened": [], "resolved": [], "snapshot": snapshot}
    for rail, (value, maximum, unit) in thresholds.items():
        incident_key = f"sync_backlog_{rail}"
        if value > maximum:
            upsert_platform_incident(
                incident_key=incident_key,
                title=f"Sync backlog breach: {rail}",
                incident_type=PlatformIncident.IncidentType.DATA,
                severity=PlatformIncident.Severity.HIGH,
                summary=(
                    f"{rail} at {value} {unit} (max {maximum} {unit}). Unresolved sync "
                    "failures accumulate silently — triage via /portal/super/sync-health/."
                ),
                source_system="sync_health",
                details={"rail": rail, "value": value, "max": maximum, "unit": unit},
            )
            outcome["opened"].append(rail)
        else:
            resolved = resolve_platform_incident(
                incident_key=incident_key,
                source_system="sync_health",
                incident_type=PlatformIncident.IncidentType.DATA,
            )
            if resolved:
                outcome["resolved"].append(rail)
    return outcome
