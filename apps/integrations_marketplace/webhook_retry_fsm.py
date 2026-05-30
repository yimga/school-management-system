"""v4.00.74 — Webhook delivery retry FSM.

Given an attempt number (1-indexed), returns the next retry interval in
seconds following the canonical schedule:

  Attempt 1 → next retry in 1m
  Attempt 2 → next retry in 5m
  Attempt 3 → next retry in 30m
  Attempt 4 → next retry in 2h
  Attempt 5 → next retry in 12h
  Attempt 6 → next retry in 24h
  Attempt 7 → exhausted (return None)

This matches the v3.31.0 ``MigrationCloudWebhookDelivery`` FSM contract
documented in ``docs/CSS_RETIREMENT_DOCKET.md``. This module is the
single source of truth — the dispatch worker and the operator UI both
import from here so the schedule never drifts.
"""
from __future__ import annotations

# Canonical retry intervals in seconds.
RETRY_SCHEDULE_SECONDS = (
    60,          # 1m
    5 * 60,      # 5m
    30 * 60,     # 30m
    2 * 60 * 60, # 2h
    12 * 60 * 60, # 12h
    24 * 60 * 60, # 24h
)
MAX_ATTEMPTS = len(RETRY_SCHEDULE_SECONDS)


def next_retry_seconds(attempt: int) -> int | None:
    """Return the seconds until the next retry given the current
    (just-failed) attempt number (1-indexed).

    Returns None when the attempt exhausted the retry budget — caller
    should mark the delivery ``exhausted`` and stop scheduling.
    """
    if attempt < 1:
        return RETRY_SCHEDULE_SECONDS[0]
    if attempt >= MAX_ATTEMPTS:
        return None  # exhausted
    return RETRY_SCHEDULE_SECONDS[attempt]


def is_exhausted(attempt: int) -> bool:
    """Return True when the delivery has used its full retry budget."""
    return attempt >= MAX_ATTEMPTS


def retry_schedule_summary() -> list[dict]:
    """Operator-facing JSON shape — used by the diagnostics UI."""
    return [
        {"attempt": i + 1, "next_retry_seconds": s,
         "next_retry_human": _human(s)}
        for i, s in enumerate(RETRY_SCHEDULE_SECONDS)
    ]


def _human(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 60 * 60:
        return f"{seconds // 60}m"
    if seconds < 24 * 60 * 60:
        return f"{seconds // (60 * 60)}h"
    return f"{seconds // (24 * 60 * 60)}d"
