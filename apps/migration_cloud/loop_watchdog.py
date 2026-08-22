"""Monotonic progression guard for long-running migration apply loops."""

from __future__ import annotations

import threading
import time
from typing import Any


class SystemicStallError(RuntimeError):
    """Raised when a loop stops advancing record pointer or mutation counts."""


class LoopWatchdog:
    """Track index + mutation delta; fail after repeated stalls or wall-clock timeout."""

    def __init__(
        self,
        *,
        max_stall_iterations: int = 3,
        timeout_seconds: float = 45.0,
        workflow_identifier: str = "",
    ) -> None:
        self.max_stall_iterations = max(1, int(max_stall_iterations))
        self.timeout_seconds = max(0.05, float(timeout_seconds))
        self.workflow_identifier = (workflow_identifier or "").strip()
        self._lock = threading.Lock()
        self._stalls = 0
        self._last_pointer: int | None = None
        self._last_mutations: int | None = None
        self._last_rows: int | None = None
        self._last_progress_at = time.monotonic()
        self._started_at = self._last_progress_at

    def heartbeat(
        self,
        *,
        current_pointer: int = 0,
        mutations_count: int = 0,
        rows_processed: int | None = None,
    ) -> None:
        """Call once per loop iteration; raises ``SystemicStallError`` on stall."""
        with self._lock:
            self._heartbeat_locked(
                current_pointer=current_pointer,
                mutations_count=mutations_count,
                rows_processed=rows_processed,
            )

    def _heartbeat_locked(
        self,
        *,
        current_pointer: int,
        mutations_count: int,
        rows_processed: int | None,
    ) -> None:
        now = time.monotonic()
        pointer = int(current_pointer)
        mutations = int(mutations_count)
        rows = int(rows_processed) if rows_processed is not None else None

        progressed = (
            self._last_pointer is None
            or pointer != self._last_pointer
            or mutations != self._last_mutations
            or (
                rows is not None
                and (self._last_rows is None or rows != self._last_rows)
            )
        )
        if progressed:
            self._stalls = 0
            self._last_progress_at = now
            self._last_pointer = pointer
            self._last_mutations = mutations
            if rows is not None:
                self._last_rows = rows
            return

        self._stalls += 1
        if self._stalls >= self.max_stall_iterations:
            raise SystemicStallError(
                f"{self.workflow_identifier or 'workflow'}: stalled at pointer "
                f"{pointer} for {self._stalls} iterations"
            )

        if now - self._last_progress_at > self.timeout_seconds:
            rows_bit = f", rows={self._last_rows}"
            raise SystemicStallError(
                f"{self.workflow_identifier or 'workflow'}: no progress for "
                f"{self.timeout_seconds:.0f}s (pointer={pointer}, "
                f"mutations={mutations}{rows_bit})"
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow_identifier,
            "stalls": self._stalls,
            "pointer": self._last_pointer,
            "mutations": self._last_mutations,
            "rows": self._last_rows,
            "elapsed_s": round(time.monotonic() - self._started_at, 3),
        }

    def __enter__(self) -> LoopWatchdog:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False
