"""v4.00.94 Wave D — proactive copilot insights queue.

Other apps push insights (anomaly detected, fee deadline approaching,
attendance dip on a roster) into this in-memory ring; the AI copilot
chip's badge resolver reports the count, and the panel surfaces the
list when the operator opens it.

In-memory, per-process, no DB. Designed for short-lived signals that go
stale within minutes. Persistence + cross-worker fanout land later.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# Severity levels — match BadgeSnapshot levels for consistency.
INSIGHT_INFO = "info"
INSIGHT_SUCCESS = "success"
INSIGHT_WARNING = "warning"
INSIGHT_CRITICAL = "critical"
VALID_INSIGHT_LEVELS = frozenset(
    {INSIGHT_INFO, INSIGHT_SUCCESS, INSIGHT_WARNING, INSIGHT_CRITICAL}
)

# Per-user ring cap so a busy tenant doesn't blow process memory.
MAX_PER_USER = 32
INSIGHT_TTL_SECONDS = 30 * 60  # 30 minutes; sweep on read


@dataclass(frozen=True)
class Insight:
    """One actionable item the dock should surface."""

    id: str
    title: str
    body: str = ""
    level: str = INSIGHT_INFO
    page_path: str = ""             # optional — when set, only shows on that page
    cta_label: str = ""
    cta_href: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Insight.id required")
        if self.level not in VALID_INSIGHT_LEVELS:
            raise ValueError(
                f"Insight.level={self.level!r} not in {sorted(VALID_INSIGHT_LEVELS)}"
            )

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        if self.expires_at is not None and now > self.expires_at:
            return True
        return (now - self.created_at) > INSIGHT_TTL_SECONDS


_QUEUES: dict[int, deque[Insight]] = {}
_LOCK = threading.Lock()


def push_insight(user_id: int, insight: Insight) -> None:
    """Append an insight to the user's ring (in-memory) + mirror to DB.

    DB mirroring is best-effort: failure is logged at DEBUG and never
    raises. Memory remains the fast path; DB enables cross-worker
    visibility + survives process restart.
    """
    if not user_id or not isinstance(insight, Insight):
        return
    with _LOCK:
        q = _QUEUES.get(user_id)
        if q is None:
            q = deque(maxlen=MAX_PER_USER)
            _QUEUES[user_id] = q
        replaced = False
        for i, existing in enumerate(q):
            if existing.id == insight.id:
                q[i] = insight
                replaced = True
                break
        if not replaced:
            q.append(insight)
    _mirror_insight_to_db(user_id, insight)


def _mirror_insight_to_db(user_id: int, insight: Insight) -> None:
    """Wave E2 — write-through to InsightRecord. Best-effort, never raises."""
    try:
        from django.utils import timezone

        from .models import InsightRecord
    except (ImportError, RuntimeError):
        return
    try:
        expires_at = None
        if insight.expires_at is not None:
            expires_at = timezone.datetime.fromtimestamp(
                insight.expires_at, tz=timezone.utc
            )
        # tenant-isolation-allow: assist-dock-insight-mirror-user-pk-public-schema-shared
        InsightRecord.objects.update_or_create(
            user_id=user_id,
            insight_id=insight.id,
            defaults={
                "title": insight.title[:200],
                "body": insight.body or "",
                "level": insight.level,
                "page_path": insight.page_path or "",
                "cta_label": insight.cta_label or "",
                "cta_href": insight.cta_href or "",
                "expires_at": expires_at,
            },
        )
    except Exception as exc:  # noqa: BLE001 — best-effort write-through
        logger.debug("insight DB mirror for user=%s failed: %s", user_id, exc)


def list_insights(user_id: int, *, page_path: str = "") -> list[Insight]:
    """Return non-expired insights for the user (optionally page-scoped).

    Reads in-memory first (fast path). If the in-memory ring is empty
    for this user (cold worker, process restart), falls back to the
    DB-backed InsightRecord table and hydrates the ring opportunistically.
    """
    if not user_id:
        return []
    with _LOCK:
        q = _QUEUES.get(user_id)
        if q is not None:
            now = time.time()
            active = [i for i in q if not i.is_expired(now)]
            if len(active) != len(q):
                q.clear()
                q.extend(active)
            if active:
                if page_path:
                    return [
                        i for i in active if not i.page_path or i.page_path == page_path
                    ]
                return list(active)
    hydrated = _hydrate_insights_from_db(user_id)
    if not hydrated:
        return []
    if page_path:
        return [i for i in hydrated if not i.page_path or i.page_path == page_path]
    return hydrated


def _hydrate_insights_from_db(user_id: int) -> list[Insight]:
    """Wave E2 — pull active InsightRecord rows into the in-memory ring."""
    try:
        from django.utils import timezone

        from .models import InsightRecord
    except (ImportError, RuntimeError):
        return []
    try:
        now = timezone.now()
        # tenant-isolation-allow: assist-dock-insight-hydrate-user-pk-public-schema-shared
        qs = (
            InsightRecord.objects.filter(user_id=user_id)
            .exclude(expires_at__lt=now)
            .order_by("-created_at")[:MAX_PER_USER]
        )
        rows = list(qs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("insight DB hydrate for user=%s failed: %s", user_id, exc)
        return []
    if not rows:
        return []
    hydrated: list[Insight] = []
    for row in rows:
        try:
            insight = Insight(
                id=row.insight_id,
                title=row.title,
                body=row.body or "",
                level=row.level,
                page_path=row.page_path or "",
                cta_label=row.cta_label or "",
                cta_href=row.cta_href or "",
                created_at=row.created_at.timestamp(),
                expires_at=row.expires_at.timestamp() if row.expires_at else None,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
        hydrated.append(insight)
    # Repopulate the ring so subsequent reads hit memory.
    with _LOCK:
        q = _QUEUES.get(user_id)
        if q is None:
            q = deque(maxlen=MAX_PER_USER)
            _QUEUES[user_id] = q
        # Preserve any newer in-memory entries by keeping their ids visible.
        existing_ids = {i.id for i in q}
        for insight in hydrated:
            if insight.id not in existing_ids:
                q.append(insight)
    return hydrated


def clear_insight(user_id: int, insight_id: str) -> bool:
    if not user_id:
        return False
    removed_memory = False
    with _LOCK:
        q = _QUEUES.get(user_id)
        if q is not None:
            for i, existing in enumerate(q):
                if existing.id == insight_id:
                    del q[i]
                    removed_memory = True
                    break
    removed_db = _clear_insight_in_db(user_id, insight_id)
    return removed_memory or removed_db


def _clear_insight_in_db(user_id: int, insight_id: str) -> bool:
    """Wave E2 — delete the DB row mirroring an in-memory insight."""
    try:
        from .models import InsightRecord
    except (ImportError, RuntimeError):
        return False
    try:
        # tenant-isolation-allow: assist-dock-insight-clear-user-pk-public-schema-shared
        deleted, _ = InsightRecord.objects.filter(
            user_id=user_id, insight_id=insight_id
        ).delete()
        return bool(deleted)
    except Exception as exc:  # noqa: BLE001
        logger.debug("insight DB clear for user=%s failed: %s", user_id, exc)
        return False


def count_insights(user_id: int, *, page_path: str = "") -> int:
    return len(list_insights(user_id, page_path=page_path))


def reset_for_tests() -> None:
    with _LOCK:
        _QUEUES.clear()


def insight_as_jsonable(insight: Insight) -> dict:
    return {
        "id": insight.id,
        "title": str(insight.title),
        "body": str(insight.body),
        "level": insight.level,
        "page_path": insight.page_path,
        "cta_label": str(insight.cta_label),
        "cta_href": insight.cta_href,
        "created_at": insight.created_at,
    }


__all__ = [
    "INSIGHT_INFO",
    "INSIGHT_SUCCESS",
    "INSIGHT_WARNING",
    "INSIGHT_CRITICAL",
    "VALID_INSIGHT_LEVELS",
    "MAX_PER_USER",
    "INSIGHT_TTL_SECONDS",
    "Insight",
    "push_insight",
    "list_insights",
    "clear_insight",
    "count_insights",
    "reset_for_tests",
    "insight_as_jsonable",
]
