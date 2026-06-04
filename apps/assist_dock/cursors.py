"""v4.00.97 Wave G1 — pseudo-cobrowse cursor + selection broadcast.

Operators on the same page see each other's cursor positions as small
colored dots; selection text shows up as a labelled chip near the cursor.
This is NOT true real-time WebSocket co-browse — clients heartbeat the
cursor at ~4 Hz via POST + read peer cursors via the existing SSE
``context_stream`` channel (which already runs an event loop on the
server). Functionally adequate for low-velocity school-admin use; the
honest residual (true WebSocket/WebRTC bridge with 60fps cursors +
voice/screen) is disclosed in the impersonate landing copy.

In-memory, per-process, Lock-protected. TTL drops stale cursors on
read; client pauses heartbeat on visibilitychange so a backgrounded
tab doesn't keep the dot alive.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


CURSOR_TTL_SECONDS = 10
CURSOR_HEARTBEAT_SECONDS = 0.25
MAX_CURSORS_PER_PAGE = 30
PAGE_PATH_MAX_LEN = 256
SELECTION_TEXT_MAX_LEN = 200
COORD_MIN = 0.0
COORD_MAX = 100.0


@dataclass(frozen=True)
class CursorPing:
    user_id: int
    display_name: str = ""
    color_hash: int = 0
    x_pct: float = 0.0
    y_pct: float = 0.0
    selection_text: str = ""
    last_seen: float = field(default_factory=time.time)

    def is_stale(self, now: float | None = None) -> bool:
        now = now or time.time()
        return (now - self.last_seen) > CURSOR_TTL_SECONDS


# {page_path: {user_id: CursorPing}}
_BY_PAGE: dict[str, dict[int, CursorPing]] = {}
_LOCK = threading.Lock()


def _sanitize_page(page_path: str) -> str:
    if not page_path:
        return ""
    page_path = page_path[:PAGE_PATH_MAX_LEN]
    return "".join(ch for ch in page_path if ch >= " " and ch != "\x7f")


def _sanitize_selection(text: str) -> str:
    if not text:
        return ""
    text = str(text)[:SELECTION_TEXT_MAX_LEN]
    return "".join(ch for ch in text if ch >= " " and ch != "\x7f")


def _clamp_coord(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN guard
        return 0.0
    if v < COORD_MIN:
        return COORD_MIN
    if v > COORD_MAX:
        return COORD_MAX
    return v


def _color_hash_for(user_id: int) -> int:
    """Stable 0-360 hue per user id so the client can paint a consistent dot."""
    if not user_id:
        return 0
    return (int(user_id) * 137) % 360  # magic-number-allow: hue-degree-rotation


def heartbeat(
    *,
    user_id: int,
    page_path: str,
    x_pct: float,
    y_pct: float,
    display_name: str = "",
    selection_text: str = "",
) -> CursorPing | None:
    """Record / refresh a user's cursor on a page. In-memory only."""
    if not user_id:
        return None
    page = _sanitize_page(page_path)
    if not page:
        return None
    ping = CursorPing(
        user_id=user_id,
        display_name=display_name[:80] if display_name else "",
        color_hash=_color_hash_for(user_id),
        x_pct=_clamp_coord(x_pct),
        y_pct=_clamp_coord(y_pct),
        selection_text=_sanitize_selection(selection_text),
        last_seen=time.time(),
    )
    with _LOCK:
        bucket = _BY_PAGE.setdefault(page, {})
        bucket[user_id] = ping
    return ping


def list_cursors(
    *, page_path: str, exclude_user_id: int | None = None
) -> list[CursorPing]:
    """Return active cursor pings for a page, excluding the caller."""
    page = _sanitize_page(page_path)
    if not page:
        return []
    now = time.time()
    with _LOCK:
        bucket = _BY_PAGE.get(page)
        if not bucket:
            return []
        stale_ids = [uid for uid, ping in bucket.items() if ping.is_stale(now)]
        for uid in stale_ids:
            del bucket[uid]
        active = [
            p for p in bucket.values() if p.user_id != exclude_user_id
        ]
    active.sort(key=lambda p: p.user_id)
    return active[:MAX_CURSORS_PER_PAGE]


def drop_user(user_id: int) -> int:
    """Remove ``user_id`` from every page bucket. Returns count removed."""
    if not user_id:
        return 0
    removed = 0
    with _LOCK:
        for bucket in _BY_PAGE.values():
            if user_id in bucket:
                del bucket[user_id]
                removed += 1
    return removed


def reset_for_tests() -> None:
    with _LOCK:
        _BY_PAGE.clear()


def ping_as_jsonable(ping: CursorPing) -> dict:
    return {
        "user_id": ping.user_id,
        "display_name": ping.display_name,
        "color_hash": ping.color_hash,
        "x_pct": ping.x_pct,
        "y_pct": ping.y_pct,
        "selection_text": ping.selection_text,
        "last_seen": ping.last_seen,
    }


def pings_as_jsonable(pings: Iterable[CursorPing]) -> list[dict]:
    return [ping_as_jsonable(p) for p in pings]


__all__ = [
    "CURSOR_TTL_SECONDS",
    "CURSOR_HEARTBEAT_SECONDS",
    "MAX_CURSORS_PER_PAGE",
    "SELECTION_TEXT_MAX_LEN",
    "CursorPing",
    "heartbeat",
    "list_cursors",
    "drop_user",
    "reset_for_tests",
    "ping_as_jsonable",
    "pings_as_jsonable",
]
