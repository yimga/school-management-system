"""Apply stall detection — configurable timeouts + lander pulse hook."""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

_STALL_PULSE: contextvars.ContextVar[Callable[[], None] | None] = contextvars.ContextVar(
    "mc_apply_stall_pulse",
    default=None,
)

_TIER_FALLBACK_SECONDS = {
    "small": 120.0,
    "mid": 240.0,
    "large": 360.0,
    "state": 600.0,
}


def set_stall_pulse_hook(hook: Callable[[], None] | None) -> contextvars.Token:
    return _STALL_PULSE.set(hook)


def reset_stall_pulse_hook(token: contextvars.Token) -> None:
    _STALL_PULSE.reset(token)


@contextmanager
def stall_pulse_scope(hook: Callable[[], None] | None) -> Iterator[None]:
    token = set_stall_pulse_hook(hook)
    try:
        yield
    finally:
        reset_stall_pulse_hook(token)


def maybe_stall_pulse(*, every: int = 1, counter: int = 0) -> None:
    """Best-effort pulse for long lander loops (post-row materialisation)."""
    hook = _STALL_PULSE.get()
    if hook is None:
        return
    if every > 1 and counter % every != 0:
        return
    try:
        hook()
    except Exception:  # noqa: BLE001 — pulse must never break apply
        logger.debug("apply_stall: pulse hook failed", exc_info=True)


def resolve_stall_timeout_seconds(bundle: Any) -> float:
    """Tier- and row-weighted stall wall clock for ``LoopWatchdog``."""
    from .defaults import get as mc_default

    tier = str(getattr(bundle, "sla_tier", None) or "small").strip().lower()
    tier_map = mc_default("migration_cloud.apply.stall_timeout_seconds")
    if not isinstance(tier_map, dict):
        tier_map = _TIER_FALLBACK_SECONDS
    base = float(tier_map.get(tier) or tier_map.get("small") or 120.0)

    row_scale = float(mc_default("migration_cloud.apply.stall_timeout_row_scale_per_1000") or 0.0)
    rows = 0
    try:
        from .unified_progress import expected_row_total

        if getattr(bundle, "pk", None):
            rows = int(expected_row_total(bundle) or 0)
    except Exception:  # noqa: BLE001 — degrade to tier-only timeout
        rows = 0

    scaled = base + (max(rows, 0) / 1000.0) * row_scale
    min_s = float(mc_default("migration_cloud.apply.stall_timeout_min_seconds") or 90.0)
    max_s = float(mc_default("migration_cloud.apply.stall_timeout_max_seconds") or 900.0)
    return max(min_s, min(max_s, scaled))
