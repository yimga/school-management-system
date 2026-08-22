"""Continuous, monotonic migration progress — row-weighted, not file-count capped.

The four-bead kickoff train capped in-flight apply at 75%% (two stages done +
import_school at 100%%). Large files showed no movement for minutes because
progress pulsed only per artifact finished. This module maps the full pipeline
to a single 0–100%% bar driven by rows processed / rows expected, with a
per-run high-water mark so a repair queue or snapshot recompute never regresses
what the tenant already saw.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from django.db.models import Sum

from .models import BundleStatus, MigrationBundle
from .progress import APPLY_RUN_EPOCH_KEY, emit as _emit_progress

logger = logging.getLogger(__name__)

# Phase bands on the unified bar (must sum to 100).
_BAND_INGEST = 8.0
_BAND_PROFILE = 12.0
_BAND_CLASSIFY_MAP = 15.0
_BAND_APPLY = 65.0  # 35 → 99 while in flight; 100 on terminal clean settle

_UNIFIED_HWM_KEY = "unified_progress_hwm"
_STATUS_ORDER = (
    BundleStatus.PENDING,
    BundleStatus.INGESTING,
    BundleStatus.PROFILED,
    BundleStatus.CLASSIFIED,
    BundleStatus.MAPPED,
    BundleStatus.APPLYING,
    BundleStatus.APPLIED,
    BundleStatus.RECONCILED,
)


def expected_row_total(bundle: MigrationBundle) -> int:
    """Sum profiled row counts across tabular artifacts."""
    try:
        total = bundle.artifacts.filter(row_count__isnull=False).aggregate(n=Sum("row_count"))["n"]
    except Exception:  # noqa: BLE001
        logger.debug("unified_progress: row total failed bundle=%s", bundle.pk, exc_info=True)
        return 0
    return max(0, int(total or 0))


def _status_index(status: str) -> int:
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return -1


def _detection_band_percent(bundle: MigrationBundle, snapshot: dict[str, Any] | None) -> float:
    """Progress through ingest → profile → classify/map before apply starts."""
    snap = snapshot or {}
    status = getattr(bundle, "status", "") or ""
    idx = _status_index(status)
    if idx < 0:
        return 0.0

    stages = {s.get("name"): s for s in (snap.get("stages") or []) if isinstance(s, dict)}
    artifact_count = max(int(bundle.artifacts.count() or 0), 1)

    def _stage_pct(name: str) -> float:
        entry = stages.get(name) or {}
        return max(0.0, min(100.0, float(entry.get("pct") or 0)))

    ingest_idx = _status_index(BundleStatus.INGESTING)
    profile_idx = _status_index(BundleStatus.PROFILED)
    classify_idx = _status_index(BundleStatus.CLASSIFIED)
    mapped_idx = _status_index(BundleStatus.MAPPED)

    score = 0.0
    if idx >= ingest_idx:
        ingest_frac = 1.0 if idx > ingest_idx else _stage_pct("INGESTING") / 100.0
        score += _BAND_INGEST * ingest_frac
    if idx >= profile_idx:
        profile_frac = 1.0 if idx > profile_idx else _stage_pct("PROFILED") / 100.0
        score += _BAND_PROFILE * profile_frac
    if idx >= classify_idx:
        # CLASSIFIED + MAPPED share the classify/map band.
        if idx >= mapped_idx:
            score += _BAND_CLASSIFY_MAP
        else:
            classify_frac = _stage_pct("CLASSIFIED") / 100.0
            map_detail = (snap.get("live_totals") or {}).get("map_artifacts_done")
            if map_detail is not None:
                map_frac = min(1.0, int(map_detail) / artifact_count)
                classify_frac = max(classify_frac, map_frac)
            score += _BAND_CLASSIFY_MAP * classify_frac
    return score


def _apply_band_percent(
    *,
    rows_processed: int,
    rows_expected: int,
    artifacts_done: int,
    artifacts_total: int,
) -> float:
    """Map row + artifact completion into the 35–99 apply band."""
    rows_expected = max(int(rows_expected or 0), 1)
    artifacts_total = max(int(artifacts_total or 0), 1)
    row_frac = min(1.0, max(0.0, int(rows_processed) / rows_expected))
    file_frac = min(1.0, max(0.0, int(artifacts_done) / artifacts_total))
    # Rows dominate; file completion is a floor so multi-file bundles still move
    # when the current file has unknown row_count.
    combined = max(row_frac, file_frac * 0.25)
    return _BAND_INGEST + _BAND_PROFILE + _BAND_CLASSIFY_MAP + (_BAND_APPLY * combined)


def _hwm_block(bundle: MigrationBundle) -> dict[str, Any]:
    summary = getattr(bundle, "size_summary", None) or {}
    block = summary.get(_UNIFIED_HWM_KEY)
    return dict(block) if isinstance(block, dict) else {}


def _run_epoch(bundle: MigrationBundle) -> str:
    return str((getattr(bundle, "size_summary", None) or {}).get(APPLY_RUN_EPOCH_KEY) or "")


def read_monotonic_hwm(bundle: MigrationBundle) -> float:
    block = _hwm_block(bundle)
    if block.get("epoch") != _run_epoch(bundle):
        return 0.0
    try:
        return max(0.0, float(block.get("pct") or 0))
    except (TypeError, ValueError):
        return 0.0


def write_monotonic_hwm(bundle: MigrationBundle, pct: float, *, persist: bool = True) -> float:
    """Ratchet stored high-water mark for this apply run; return the stored value."""
    pct = max(0.0, min(100.0, float(pct)))
    epoch = _run_epoch(bundle)
    block = _hwm_block(bundle)
    if block.get("epoch") != epoch:
        block = {"epoch": epoch, "pct": 0.0}
    stored = max(float(block.get("pct") or 0), pct)
    block["pct"] = round(stored, 4)
    block["epoch"] = epoch
    if not persist:
        summary = {**(getattr(bundle, "size_summary", None) or {}), _UNIFIED_HWM_KEY: block}
        bundle.size_summary = summary
        return stored
    try:
        from .apply_progress_guard import _db_summary

        summary = {**_db_summary(bundle), _UNIFIED_HWM_KEY: block}
        bundle.size_summary = summary
        bundle.save(update_fields=["size_summary", "updated_at"])
    except Exception:  # noqa: BLE001
        logger.debug("unified_progress: hwm persist failed bundle=%s", bundle.pk, exc_info=True)
    return stored


def compute_unified_percent(
    bundle: MigrationBundle,
    *,
    snapshot: dict[str, Any] | None = None,
    flight: dict[str, Any] | None = None,
    in_flight: bool | None = None,
) -> dict[str, Any]:
    """Return unified percent + row counters for pollers and telemetry."""
    flight = flight or {}
    snap = snapshot or getattr(bundle, "progress_snapshot", None) or {}
    status = getattr(bundle, "status", "") or ""
    importing = in_flight if in_flight is not None else bool(flight.get("in_flight"))

    live = snap.get("live_totals") or {}
    rows_processed = int(live.get("rows_processed") or live.get("rows") or 0)
    rows_expected = int(live.get("rows_expected") or 0) or expected_row_total(bundle)
    artifacts_done = int(live.get("artifacts_done") or 0)
    artifacts_total = int(live.get("artifacts_total") or 0)

    if status in (BundleStatus.RECONCILED,):
        pct = 100.0
    elif status in (BundleStatus.APPLIED,) and not importing:
        pct = 100.0
    elif status == BundleStatus.APPLYING or importing:
        detection = _BAND_INGEST + _BAND_PROFILE + _BAND_CLASSIFY_MAP
        apply_score = _apply_band_percent(
            rows_processed=rows_processed,
            rows_expected=rows_expected,
            artifacts_done=artifacts_done,
            artifacts_total=artifacts_total,
        )
        pct = max(detection, apply_score)
        if importing:
            pct = min(pct, 99.0)
    else:
        pct = _detection_band_percent(bundle, snap)
        if importing:
            pct = min(max(pct, _BAND_INGEST + _BAND_PROFILE + _BAND_CLASSIFY_MAP), 99.0)

    hwm = read_monotonic_hwm(bundle)
    pct = max(pct, hwm)
    if importing or status == BundleStatus.APPLYING:
        pct = write_monotonic_hwm(bundle, pct, persist=False)

    return {
        "percent": round(pct, 2),
        "rows_processed": rows_processed,
        "rows_expected": rows_expected,
        "artifacts_done": artifacts_done,
        "artifacts_total": artifacts_total,
    }


def pulse_detection_progress(
    *,
    bundle_id: int,
    stage: str,
    message: str,
    artifacts_done: int,
    artifacts_total: int,
) -> None:
    """Emit incremental progress while profiling / classifying / mapping."""
    artifacts_total = max(int(artifacts_total or 0), 1)
    pct = int(round(100 * int(artifacts_done) / artifacts_total))
    detail: dict[str, Any] = {
        "pct": pct,
        "artifacts_done": int(artifacts_done),
        "artifacts_total": artifacts_total,
    }
    if stage == "CLASSIFIED":
        detail["map_artifacts_done"] = int(artifacts_done)
    _emit_progress(
        bundle_id=bundle_id,
        kind="artifact_progress",
        stage=stage[:32],
        message=message[:2000],
        detail=detail,
    )


def pulse_apply_progress(
    *,
    bundle_id: int,
    bundle: MigrationBundle,
    message: str,
    rows_processed: int,
    rows_expected: int,
    artifacts_done: int,
    artifacts_total: int,
    created: int,
    updated: int,
    quarantined: int,
    wave: int = 0,
) -> float:
    """Emit apply-band progress; return unified percent for callers."""
    rows_expected = max(int(rows_expected or 0), 1)
    artifacts_total = max(int(artifacts_total or 0), 1)
    apply_pct = int(
        round(
            100
            * max(
                rows_processed / rows_expected,
                artifacts_done / artifacts_total * 0.25,
            )
        )
    )
    detail = {
        "pct": apply_pct,
        "rows": int(rows_processed),
        "rows_processed": int(rows_processed),
        "rows_expected": int(rows_expected),
        "artifacts_done": int(artifacts_done),
        "artifacts_total": int(artifacts_total),
        "created": int(created),
        "updated": int(updated),
        "quarantined": int(quarantined),
        "held": int(quarantined),
        "wave": int(wave),
    }
    _emit_progress(
        bundle_id=bundle_id,
        kind="artifact_progress",
        stage="APPLYING",
        message=message[:2000],
        detail=detail,
    )
    unified = compute_unified_percent(
        bundle,
        in_flight=True,
    )
    write_monotonic_hwm(bundle, unified["percent"], persist=True)
    return unified["percent"]


class RowProgressIterator:
    """Count rows consumed by a lander and pulse throttled progress events."""

    def __init__(
        self,
        rows: Any,
        *,
        tracker: ApplyProgressTracker,
        artifact_label: str,
    ) -> None:
        self._rows = rows
        self._tracker = tracker
        self._artifact_label = artifact_label
        self._count = 0
        self._last_pulse = 0.0

    def __iter__(self):
        for row in self._rows:
            self._count += 1
            self._tracker.register_row(self._count, artifact_label=self._artifact_label)
            yield row

    @property
    def rows_seen(self) -> int:
        return self._count


class ApplyProgressTracker:
    """Row- and artifact-aware apply progress for one bundle run."""

    def __init__(
        self,
        *,
        bundle: MigrationBundle,
        jobs_total: int,
        rows_expected: int | None = None,
        pulse_every_rows: int = 40,
        min_pulse_seconds: float = 0.45,
        on_stall_heartbeat: Callable[[], None] | None = None,
    ) -> None:
        self.bundle = bundle
        self.bundle_id = int(bundle.pk)
        self.jobs_total = max(int(jobs_total or 0), 1)
        self.rows_expected = max(int(rows_expected or 0) or expected_row_total(bundle), 1)
        self._pulse_every_rows = max(1, int(pulse_every_rows))
        self._min_pulse_seconds = max(0.1, float(min_pulse_seconds))
        self.on_stall_heartbeat = on_stall_heartbeat
        self._rows_global = 0
        self._artifacts_done = 0
        self._last_pulse_at = 0.0
        self._running_totals = {"created": 0, "updated": 0, "quarantined": 0}
        self._lock = threading.Lock()

    @property
    def rows_global(self) -> int:
        with self._lock:
            return self._rows_global

    def wrap_rows(self, rows: Any, *, artifact_label: str) -> RowProgressIterator:
        return RowProgressIterator(rows, tracker=self, artifact_label=artifact_label)

    def register_row(self, rows_in_artifact: int, *, artifact_label: str = "") -> None:
        with self._lock:
            self._rows_global += 1
            rows_global = self._rows_global
            last_pulse = self._last_pulse_at
        now = time.monotonic()
        if (
            rows_in_artifact % self._pulse_every_rows == 0
            or now - last_pulse >= self._min_pulse_seconds
        ):
            label = artifact_label or "file"
            self.pulse(
                message=f"Importing {label} — row {rows_in_artifact:,} "
                f"({rows_global:,}/{self.rows_expected:,} total)",
                wave=-1,
            )
            self._maybe_stall_heartbeat()

    def _maybe_stall_heartbeat(self) -> None:
        hook = self.on_stall_heartbeat
        if hook is None:
            return
        try:
            hook()
        except Exception:  # noqa: BLE001 — stall hook must never break apply
            logger.debug(
                "unified_progress: stall heartbeat failed bundle=%s",
                self.bundle_id,
                exc_info=True,
            )

    def absorb_outcomes(self, outcomes: list[Any]) -> None:
        with self._lock:
            self._artifacts_done = len(outcomes)
            created = updated = quarantined = 0
            for outcome in outcomes:
                result = getattr(outcome, "result", None)
                if result is None:
                    continue
                created += int(getattr(result, "created", 0) or 0)
                updated += int(getattr(result, "updated", 0) or 0)
                quarantined += int(getattr(result, "quarantined", 0) or 0)
            self._running_totals = {
                "created": created,
                "updated": updated,
                "quarantined": quarantined,
            }

    def pulse(self, *, message: str, wave: int) -> None:
        with self._lock:
            self._last_pulse_at = time.monotonic()
            rows_processed = self._rows_global
            artifacts_done = self._artifacts_done
            totals = dict(self._running_totals)
        pulse_apply_progress(
            bundle_id=self.bundle_id,
            bundle=self.bundle,
            message=message,
            rows_processed=rows_processed,
            rows_expected=self.rows_expected,
            artifacts_done=artifacts_done,
            artifacts_total=self.jobs_total,
            created=totals["created"],
            updated=totals["updated"],
            quarantined=totals["quarantined"],
            wave=wave,
        )

    def on_artifact_complete(self, outcomes: list[Any], *, wave_index: int) -> None:
        self.absorb_outcomes(outcomes)
        totals = self._running_totals
        done = self._artifacts_done
        self.pulse(
            message=(
                f"Imported {totals['created']} new, {totals['updated']} updated, "
                f"{totals['quarantined']} held ({done}/{self.jobs_total} files, "
                f"{self._rows_global:,}/{self.rows_expected:,} rows)"
            ),
            wave=wave_index,
        )
