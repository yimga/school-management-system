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
    """Record / refresh a user's presence on a page (memory + DB mirror)."""
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
    # Wave F1 — best-effort DB mirror so other workers see this user too.
    _mirror_heartbeat_to_db(entry=entry, page_path=page)
    return entry


def _mirror_heartbeat_to_db(*, entry: PresenceEntry, page_path: str) -> None:
    """Wave F1 — upsert PresencePing row. Best-effort, never raises."""
    try:
        from .models import PresencePing
    except (ImportError, RuntimeError):
        return
    try:
        # tenant-isolation-allow: assist-dock-presence-mirror-user-pk-public-schema-shared
        PresencePing.objects.update_or_create(
            user_id=entry.user_id,
            page_path=page_path[:PAGE_PATH_MAX_LEN],
            defaults={
                "display_name": entry.display_name[:80],
                "avatar_url": entry.avatar_url[:512],
            },
        )
    except Exception:  # noqa: BLE001 — best-effort write-through
        pass


def list_present(*, page_path: str, exclude_user_id: int | None = None) -> list[PresenceEntry]:
    """Return active presence entries for a page (memory + DB merged).

    Wave F1: walk the in-process bucket first (sub-ms), then merge in any
    PresencePing rows from OTHER workers whose ``last_seen`` is fresh.
    Memory wins on conflict (a user with both layers visible counts once).
    """
    page = _sanitize_page(page_path)
    if not page:
        return []
    now = time.time()
    with _LOCK:
        bucket = _BY_PAGE.get(page)
        if bucket:
            stale_ids = [uid for uid, entry in bucket.items() if entry.is_stale(now)]
            for uid in stale_ids:
                del bucket[uid]
        active = [
            e
            for e in (bucket or {}).values()
            if e.user_id != exclude_user_id
        ]
    seen_ids = {e.user_id for e in active}
    db_entries = _list_present_from_db(page_path=page, exclude_user_id=exclude_user_id)
    for entry in db_entries:
        if entry.user_id in seen_ids:
            continue
        active.append(entry)
        seen_ids.add(entry.user_id)
    active.sort(key=lambda e: e.first_seen)
    return active[:MAX_PER_PAGE]


def _list_present_from_db(*, page_path: str, exclude_user_id: int | None) -> list[PresenceEntry]:
    """Wave F1 — pull fresh PresencePing rows from other workers."""
    try:
        from datetime import timedelta

        from django.utils import timezone

        from .models import PresencePing
    except (ImportError, RuntimeError):
        return []
    try:
        cutoff = timezone.now() - timedelta(seconds=PRESENCE_TTL_SECONDS)
        # tenant-isolation-allow: assist-dock-presence-list-from-db-public-schema-shared
        qs = (
            PresencePing.objects.filter(
                page_path=page_path[:PAGE_PATH_MAX_LEN],
                last_seen__gte=cutoff,
            )
            .exclude(user_id=exclude_user_id or 0)
            .order_by("first_seen")[: MAX_PER_PAGE * 2]
        )
        rows = list(qs)
    except Exception:  # noqa: BLE001
        return []
    out: list[PresenceEntry] = []
    for row in rows:
        try:
            out.append(
                PresenceEntry(
                    user_id=row.user_id,
                    display_name=row.display_name or "",
                    avatar_url=row.avatar_url or "",
                    first_seen=row.first_seen.timestamp() if row.first_seen else 0,
                    last_seen=row.last_seen.timestamp() if row.last_seen else 0,
                )
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
    return out


def sweep_db_presence(*, ttl_seconds: int = PRESENCE_TTL_SECONDS) -> int:
    """Wave F1 — bulk-delete stale PresencePing rows. Returns deleted count.

    Designed to be safe to call from a Celery beat OR opportunistically
    from heartbeat. Never raises.
    """
    try:
        from datetime import timedelta

        from django.utils import timezone

        from .models import PresencePing
    except (ImportError, RuntimeError):
        return 0
    try:
        cutoff = timezone.now() - timedelta(seconds=max(ttl_seconds, 0))
        # tenant-isolation-allow: assist-dock-presence-sweep-stale-public-schema-shared
        deleted, _ = PresencePing.objects.filter(last_seen__lt=cutoff).delete()
        return int(deleted)
    except Exception:  # noqa: BLE001
        return 0


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
