"""v4.00.95 Wave E1 — presence tracker.

Records which authenticated users are currently looking at each page.
Other operators on the same page show up as small avatars on the
presence chip; clicking opens a list.

In-memory, per-process, Lock-protected. Heartbeat from JS every 30s
keeps the entry alive; entries older than ``PRESENCE_TTL_SECONDS``
are swept on read. Cross-worker fanout is deferred to a later wave
(would need Redis pub/sub or a DB-backed presence row).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


PRESENCE_TTL_SECONDS = 90        # entries older than this are dropped
PRESENCE_HEARTBEAT_SECONDS = 30  # client-side cadence advertised to JS
MAX_PER_PAGE = 50                # cap returned list so a busy page doesn't explode
PAGE_PATH_MAX_LEN = 256


@dataclass(frozen=True)
class PresenceEntry:
    user_id: int
    display_name: str = ""
    avatar_url: str = ""
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def is_stale(self, now: float | None = None) -> bool:
        now = now or time.time()
        return (now - self.last_seen) > PRESENCE_TTL_SECONDS


# {page_path: {user_id: PresenceEntry}}
_BY_PAGE: dict[str, dict[int, PresenceEntry]] = {}
_LOCK = threading.Lock()


def _sanitize_page(page_path: str) -> str:
    if not page_path:
        return ""
    page_path = page_path[:PAGE_PATH_MAX_LEN]
    return "".join(ch for ch in page_path if ch >= " " and ch != "\x7f")


def heartbeat(
    *,
    user_id: int,
    page_path: str,
    display_name: str = "",
    avatar_url: str = "",
) -> PresenceEntry | None:
    """Record / refresh a user's presence on a page."""
    if not user_id:
        return None
    page = _sanitize_page(page_path)
    if not page:
        return None
    now = time.time()
    with _LOCK:
        bucket = _BY_PAGE.setdefault(page, {})
        existing = bucket.get(user_id)
        if existing is not None and not existing.is_stale(now):
            entry = PresenceEntry(
                user_id=user_id,
                display_name=display_name or existing.display_name,
                avatar_url=avatar_url or existing.avatar_url,
                first_seen=existing.first_seen,
                last_seen=now,
            )
        else:
            entry = PresenceEntry(
                user_id=user_id,
                display_name=display_name,
                avatar_url=avatar_url,
                first_seen=now,
                last_seen=now,
            )
        bucket[user_id] = entry
        return entry


def list_present(*, page_path: str, exclude_user_id: int | None = None) -> list[PresenceEntry]:
    """Return active presence entries for a page (optionally excluding self)."""
    page = _sanitize_page(page_path)
    if not page:
        return []
    now = time.time()
    with _LOCK:
        bucket = _BY_PAGE.get(page)
        if not bucket:
            return []
        # Sweep stale.
        stale_ids = [uid for uid, entry in bucket.items() if entry.is_stale(now)]
        for uid in stale_ids:
            del bucket[uid]
        if not bucket:
            return []
        active = [e for e in bucket.values() if e.user_id != exclude_user_id]
    active.sort(key=lambda e: e.first_seen)
    return active[:MAX_PER_PAGE]


def count_present(*, page_path: str, exclude_user_id: int | None = None) -> int:
    return len(list_present(page_path=page_path, exclude_user_id=exclude_user_id))


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


def entry_as_jsonable(entry: PresenceEntry) -> dict:
    return {
        "user_id": entry.user_id,
        "display_name": entry.display_name or "",
        "avatar_url": entry.avatar_url or "",
        "first_seen": entry.first_seen,
        "last_seen": entry.last_seen,
    }


def entries_as_jsonable(entries: Iterable[PresenceEntry]) -> list[dict]:
    return [entry_as_jsonable(e) for e in entries]


__all__ = [
    "PRESENCE_TTL_SECONDS",
    "PRESENCE_HEARTBEAT_SECONDS",
    "MAX_PER_PAGE",
    "PresenceEntry",
    "heartbeat",
    "list_present",
    "count_present",
    "drop_user",
    "reset_for_tests",
    "entry_as_jsonable",
    "entries_as_jsonable",
]
