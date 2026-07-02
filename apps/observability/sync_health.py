"""Cross-rail sync health (9.8 sync-observability wave, 2026-07-02).

The platform has THREE offline/sync rails whose failures land in three
different stores with wildly different visibility:

  * delta-sync   -> ``SyncConflict`` rows (operator SLO dashboard sees these)
  * SODP queue   -> ``OfflineAction`` rows (tenant portal only — no operator
                    rollup existed before this module)
  * WAL/oplog    -> Redis review streams ``rmc.wal.deadletter.<hash>`` and
                    ``rmc.wal.conflict.<hash>`` (write-only before this module:
                    no reader, UI, metric, or alert anywhere in the codebase)

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
        "wal": _collect_wal(client),
    }
    emit_gauge("rmc.sync.sodp.queued", snapshot["sodp"]["queued"])
    emit_gauge("rmc.sync.sodp.failed", snapshot["sodp"]["failed"])
    emit_gauge("rmc.sync.sodp.conflict", snapshot["sodp"]["conflict"])
    emit_gauge("rmc.sync.delta.pending", snapshot["delta"]["pending"])
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
    """
    from apps.observability.incident_services import (
        resolve_platform_incident,
        upsert_platform_incident,
    )
    from apps.observability.models import PlatformIncident

    if snapshot is None:
        snapshot = collect_sync_health(redis_client=redis_client)
    thresholds = {
        "sodp_conflict": (
            snapshot["sodp"]["conflict"],
            int(getattr(settings, "RMC_SYNC_SODP_CONFLICT_MAX", 25)),
        ),
        "delta_pending": (
            snapshot["delta"]["pending"],
            int(getattr(settings, "SYNC_CONFLICT_PENDING_SLO_MAX", 10)),
        ),
        "wal_deadletter": (
            snapshot["wal"]["deadletter_depth"],
            int(getattr(settings, "RMC_SYNC_WAL_DEADLETTER_MAX", 10)),
        ),
    }
    outcome: dict[str, Any] = {"opened": [], "resolved": [], "snapshot": snapshot}
    for rail, (value, maximum) in thresholds.items():
        incident_key = f"sync_backlog_{rail}"
        if value > maximum:
            upsert_platform_incident(
                incident_key=incident_key,
                title=f"Sync backlog breach: {rail}",
                incident_type=PlatformIncident.IncidentType.DATA,
                severity=PlatformIncident.Severity.HIGH,
                summary=(
                    f"{rail} at {value} (max {maximum}). Unresolved sync failures "
                    "accumulate silently — triage via /portal/super/sync-health/."
                ),
                source_system="sync_health",
                details={"rail": rail, "value": value, "max": maximum},
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
