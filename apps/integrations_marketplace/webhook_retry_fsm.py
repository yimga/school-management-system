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
    # v4.01 — attempt is 1-indexed, so the delay after attempt N is
    # SCHEDULE[N-1]. The previous SCHEDULE[attempt] skipped SCHEDULE[0]
    # entirely (the first interval was never used) and disagreed with
    # retry_schedule_summary(), which maps attempt i+1 -> SCHEDULE[i].
    return RETRY_SCHEDULE_SECONDS[attempt - 1]


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


# v4.00.81 — Per-provider retry budget overrides.
#
# Defaults to MAX_ATTEMPTS for any provider not in the table. Override
# via RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS env (JSON dict provider->int).
# Values clamped to [1, 20] to bound blast radius (a provider misconfigured
# to MAX_INT would burn the queue).
_PROVIDER_RETRY_BUDGET_FLOOR = 1
_PROVIDER_RETRY_BUDGET_CEILING = 20

_DEFAULT_PROVIDER_RETRY_BUDGETS: dict[str, int] = {
    # Provider-specific defaults (operator can override via env)
    # E.g. "pagerduty": 3 -> give up faster on alerting webhooks
}


def _resolve_provider_retry_budgets() -> dict[str, int]:
    """Read RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS env (JSON). Falls back to
    _DEFAULT_PROVIDER_RETRY_BUDGETS. Never raises — bad JSON ignored."""
    try:
        import json
        import os
        raw = os.environ.get("RMC_WEBHOOK_PROVIDER_RETRY_BUDGETS", "")
        if not raw:
            return dict(_DEFAULT_PROVIDER_RETRY_BUDGETS)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return dict(_DEFAULT_PROVIDER_RETRY_BUDGETS)
        out = dict(_DEFAULT_PROVIDER_RETRY_BUDGETS)
        for k, v in parsed.items():
            if not isinstance(k, str):
                continue
            try:
                vi = int(v)
            except (TypeError, ValueError):
                continue
            # Clamp
            vi = max(_PROVIDER_RETRY_BUDGET_FLOOR, min(_PROVIDER_RETRY_BUDGET_CEILING, vi))
            out[k] = vi
        return out
    except Exception:  # noqa: BLE001
        return dict(_DEFAULT_PROVIDER_RETRY_BUDGETS)


def max_attempts_for_provider(provider: str) -> int:
    """Return the effective MAX_ATTEMPTS for ``provider``. Falls back to
    the global MAX_ATTEMPTS when no per-provider override exists."""
    budgets = _resolve_provider_retry_budgets()
    return int(budgets.get(provider, MAX_ATTEMPTS))


def next_retry_seconds_for_provider(*, provider: str, attempt: int) -> int | None:
    """Return next-retry seconds for ``provider`` AT ``attempt``. Returns
    None when the per-provider budget is exhausted. ``attempt`` is 1-based."""
    cap = max_attempts_for_provider(provider)
    if attempt < 1 or attempt > cap:
        return None
    # Use the same schedule curve, but cap by the per-provider budget.
    # For attempts beyond the schedule length, repeat the last interval.
    if attempt <= len(RETRY_SCHEDULE_SECONDS):
        return RETRY_SCHEDULE_SECONDS[attempt - 1]
    return RETRY_SCHEDULE_SECONDS[-1]


def is_exhausted_for_provider(*, provider: str, attempt: int) -> bool:
    """True when ``attempt`` >= per-provider budget."""
    return attempt >= max_attempts_for_provider(provider)
