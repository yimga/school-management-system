"""v4.00.91 Wave B — pluggable badge resolver registry.

Each chip in the dock can carry a live badge (count, dot, severity level).
The badge resolver is a small callable that other apps register against a
slot id; it runs server-side per request and the result lands in the
``/assist-dock/context/`` JSON payload the JS polls.

Resolver contract:

    def resolver(request, *, slot, page_path) -> BadgeSnapshot | None:
        ...

Return ``None`` to suppress the badge (resolver decided there's nothing to
show). Resolvers should be **fast** (under 50 ms wall clock) and tolerant
of missing tenant context — they run on every page request.

Resolvers are pure code; no DB schema is added by this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# Severity levels for the badge — drives the JS pill colour.
BADGE_LEVEL_INFO = "info"
BADGE_LEVEL_SUCCESS = "success"
BADGE_LEVEL_WARNING = "warning"
BADGE_LEVEL_CRITICAL = "critical"
VALID_BADGE_LEVELS = frozenset(
    {BADGE_LEVEL_INFO, BADGE_LEVEL_SUCCESS, BADGE_LEVEL_WARNING, BADGE_LEVEL_CRITICAL}
)


@dataclass(frozen=True)
class BadgeSnapshot:
    """One badge frame for a chip.

    ``count`` is the integer that renders inside the pill (None = no number,
    dot only). ``dot`` is the always-on indicator (True = unread / new).
    ``level`` is one of the BADGE_LEVEL_* constants — drives colour.
    ``tooltip`` is an optional short hover string.
    """

    count: Optional[int] = None
    dot: bool = False
    level: str = BADGE_LEVEL_INFO
    tooltip: str = ""

    def __post_init__(self) -> None:
        if self.level not in VALID_BADGE_LEVELS:
            raise ValueError(
                f"BadgeSnapshot.level={self.level!r} not in {sorted(VALID_BADGE_LEVELS)}"
            )
        if self.count is not None and self.count < 0:
            raise ValueError("BadgeSnapshot.count must be >= 0 when set")

    def as_jsonable(self) -> dict:
        return {
            "count": self.count,
            "dot": bool(self.dot),
            "level": self.level,
            "tooltip": self.tooltip or "",
        }


BadgeResolver = Callable[..., Optional[BadgeSnapshot]]
_RESOLVERS: dict[str, BadgeResolver] = {}


def register_badge_resolver(slot_id: str, resolver: BadgeResolver) -> None:
    """Bind a resolver to a slot. Re-registering overwrites the previous one."""
    if not slot_id:
        raise ValueError("register_badge_resolver requires a non-empty slot_id")
    if not callable(resolver):
        raise TypeError("register_badge_resolver requires a callable")
    _RESOLVERS[slot_id] = resolver


def unregister_badge_resolver(slot_id: str) -> bool:
    return _RESOLVERS.pop(slot_id, None) is not None


def get_badge_resolver(slot_id: str) -> Optional[BadgeResolver]:
    return _RESOLVERS.get(slot_id)


def resolve_badge(request, *, slot, page_path: str = "") -> Optional[dict]:
    """Run the resolver for ``slot`` and return the jsonable payload.

    Defensive: any exception is swallowed + logged at DEBUG; the dock never
    breaks because a single badge resolver crashed.
    """
    resolver = _RESOLVERS.get(slot.id)
    if resolver is None:
        return None
    try:
        snap = resolver(request, slot=slot, page_path=page_path)
    except Exception as exc:  # noqa: BLE001 — badge layer is best-effort
        logger.debug("badge resolver for %s failed: %s", slot.id, exc)
        return None
    if snap is None:
        return None
    if not isinstance(snap, BadgeSnapshot):
        logger.debug("badge resolver for %s returned non-BadgeSnapshot", slot.id)
        return None
    return snap.as_jsonable()


def resolve_all_badges(request, *, slots, page_path: str = "") -> dict[str, dict]:
    """Resolve badges for a list of slots — returns ``{slot_id: payload}``."""
    out: dict[str, dict] = {}
    for slot in slots:
        payload = resolve_badge(request, slot=slot, page_path=page_path)
        if payload is not None:
            out[slot.id] = payload
    return out


def reset_resolvers_for_tests() -> None:
    """Clear the resolver registry. Tests only."""
    _RESOLVERS.clear()


__all__ = [
    "BADGE_LEVEL_INFO",
    "BADGE_LEVEL_SUCCESS",
    "BADGE_LEVEL_WARNING",
    "BADGE_LEVEL_CRITICAL",
    "VALID_BADGE_LEVELS",
    "BadgeSnapshot",
    "BadgeResolver",
    "register_badge_resolver",
    "unregister_badge_resolver",
    "get_badge_resolver",
    "resolve_badge",
    "resolve_all_badges",
    "reset_resolvers_for_tests",
]
