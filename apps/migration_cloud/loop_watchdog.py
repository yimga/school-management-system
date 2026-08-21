"""Monotonic progression guard for long-running migration apply loops."""

from __future__ import annotations

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
        self._stalls = 0
        self._last_pointer: int | None = None
        self._last_mutations: int | None = None
        self._last_progress_at = time.monotonic()
        self._started_at = self._last_progress_at

    def heartbeat(
        self,
        *,
        current_pointer: int = 0,
        mutations_count: int = 0,
    ) -> None:
        """Call once per loop iteration; raises ``SystemicStallError`` on stall."""
        now = time.monotonic()
        if now - self._last_progress_at > self.timeout_seconds:
            raise SystemicStallError(
                f"{self.workflow_identifier or 'workflow'}: no progress for "
                f"{self.timeout_seconds:.0f}s (pointer={current_pointer}, "
                f"mutations={mutations_count})"
            )

        pointer = int(current_pointer)
        mutations = int(mutations_count)
        if (
            self._last_pointer is not None
            and pointer == self._last_pointer
            and mutations == self._last_mutations
        ):
            self._stalls += 1
            if self._stalls >= self.max_stall_iterations:
                raise SystemicStallError(
                    f"{self.workflow_identifier or 'workflow'}: stalled at pointer "
                    f"{pointer} for {self._stalls} iterations"
                )
        else:
            self._stalls = 0
            self._last_progress_at = now

        self._last_pointer = pointer
        self._last_mutations = mutations

    def snapshot(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow_identifier,
            "stalls": self._stalls,
            "pointer": self._last_pointer,
            "mutations": self._last_mutations,
            "elapsed_s": round(time.monotonic() - self._started_at, 3),
        }

    def __enter__(self) -> LoopWatchdog:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False
