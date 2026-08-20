"""Stop re-applying a bundle that has already proven it changes nothing.

The failure this exists to prevent (observed live on 2026-08-20, bundle 84 of the
gilead-tech tenant): eighty-five ``mc_apply_bundle`` outbox rows, eighty-four of
them ``succeeded``, every one reporting the IDENTICAL result --
``0 created, 105 updated, 442 quarantined`` -- with a fresh row minted one to two
seconds after each finished. It had been running since 2026-08-16. Four days of a
worker pinned at 100%, importing nothing, on the same Render instance that serves
the tenant and answers edge sync; the 502s and read-timeouts the box reported are
consistent with that starvation.

Two properties combined to make it unbounded:

1. ``enqueue_heavy_work`` dedupes an idempotency key only against ``pending`` /
   ``processing`` rows. The instant an apply reaches ``succeeded`` the key
   ``mc-apply:<id>:live:active`` is free again, so the very next caller mints a
   brand-new row rather than being handed the finished one.
2. Nothing anywhere asked whether the previous apply had accomplished anything.
   A re-apply that produces byte-identical totals is not a retry; it is the same
   computation performed again, and it will produce the same totals next time.

Note what does NOT work here, because it is the obvious fix: keying the
idempotency string on the apply-run epoch. ``progress.mark_apply_run_start`` is
called by the orchestrator on *entry* to APPLYING (orchestrator.py:269), so the
epoch changes on every single run -- an epoch-scoped key is a different key each
time and dedupes nothing.

So the guard is on forward progress instead, which is the property actually being
violated, and it holds no matter which caller fires. There are seven enqueue sites
(intake promotion, the operator apply view, the tenant apply view, repair, the
workflow fix handler, ``mc_recover_import``, and the post-apply reconcile chain);
identifying which one is looping on a given deployment is an operations question,
but none of them should be able to loop, and after this none of them can.

The rule: a LIVE apply that returns the same ``(created, updated, quarantined,
status)`` as the previous live apply AND created no rows counts as no progress.
``RMC_MC_APPLY_NO_PROGRESS_LIMIT`` consecutive such applies (default 3) and the
bundle stops accepting automatic re-applies.

Requiring ``created == 0`` is deliberate conservatism: a bundle genuinely
inserting rows is making progress and must never be blocked, even if its totals
happen to repeat. The cost of that choice is that a pathological bundle which
creates rows every pass keeps running -- but that bundle is doing real work, and
"it is importing" is a different problem from "it is spinning".

A human is never blocked. ``repair_bundle`` passes ``force=True`` and calls
:func:`reset_apply_progress`, so clicking Repair always re-arms the budget. The
breaker bounds AUTOMATIC re-entry only.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Key under ``MigrationBundle.size_summary`` holding the progress block.
APPLY_PROGRESS_KEY = "apply_progress"

# Consecutive no-progress applies tolerated before automatic re-apply is refused.
DEFAULT_NO_PROGRESS_LIMIT = 3


def no_progress_limit() -> int:
    """Configured streak limit, floored at 1 so the breaker can never be disabled
    into an infinite loop by a bad value."""
    raw = getattr(settings, "RMC_MC_APPLY_NO_PROGRESS_LIMIT", DEFAULT_NO_PROGRESS_LIMIT)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_NO_PROGRESS_LIMIT


def outcome_fingerprint(
    *, created: int, updated: int, quarantined: int, status: str
) -> str:
    """Stable short digest of one apply's observable result."""
    raw = f"{int(created)}|{int(updated)}|{int(quarantined)}|{str(status or '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _db_summary(bundle) -> dict[str, Any]:
    """``size_summary`` as the database currently holds it.

    Falls back to the in-memory copy when the row cannot be read (unsaved bundle
    in a test, or a deleted row), so callers always get a dict.
    """
    try:
        from .models import MigrationBundle

        fresh = (
            MigrationBundle.objects  # tenant-isolation-allow: bundle-progress-bookkeeping-by-pk
            .filter(pk=bundle.pk)
            .values_list("size_summary", flat=True)
            .first()
        )
        if isinstance(fresh, dict):
            return fresh
    except Exception:  # noqa: BLE001 — fall back to the in-memory copy
        logger.debug("apply_progress_guard: summary read failed", exc_info=True)
    return getattr(bundle, "size_summary", None) or {}


def _progress_block(bundle, *, from_db: bool = False) -> dict[str, Any]:
    summary = _db_summary(bundle) if from_db else (getattr(bundle, "size_summary", None) or {})
    block = summary.get(APPLY_PROGRESS_KEY)
    return dict(block) if isinstance(block, dict) else {}


def no_progress_streak(bundle) -> int:
    """How many consecutive live applies changed nothing. 0 when unknown."""
    try:
        return max(0, int(_progress_block(bundle).get("no_progress_streak") or 0))
    except (TypeError, ValueError):
        return 0


def apply_is_livelocked(bundle, *, limit: int | None = None) -> bool:
    """True when automatic re-apply of this bundle must stop.

    Never raises: a guard that blows up would take out the apply path it is meant
    to protect, which is strictly worse than the livelock it prevents.
    """
    try:
        cap = no_progress_limit() if limit is None else max(1, int(limit))
        return no_progress_streak(bundle) >= cap
    except Exception:  # noqa: BLE001 — a broken guard must not block a real import
        logger.debug(
            "apply_progress_guard: livelock check failed bundle=%s",
            getattr(bundle, "pk", "?"),
            exc_info=True,
        )
        return False


def _save_block(bundle, block: dict[str, Any]) -> None:
    """Merge the progress block into ``size_summary`` without losing sibling keys.

    The merge base is re-read from the database rather than taken from the
    in-memory instance: an apply calls ``mark_status`` several times between
    ``mark_apply_run_start`` and here, and each of those patches ``size_summary``.
    Writing a stale in-memory copy back would silently drop whatever those wrote —
    including ``apply_run_started_at``, which the progress snapshot uses as its
    run boundary.
    """
    summary = {**_db_summary(bundle), APPLY_PROGRESS_KEY: block}
    bundle.size_summary = summary
    # size_summary only — never disturb a status transition the caller is making.
    bundle.save(update_fields=["size_summary", "updated_at"])


def record_apply_outcome(
    bundle, *, created: int, updated: int, quarantined: int, status: str
) -> dict[str, Any]:
    """Record one LIVE apply's result and update the no-progress streak.

    Returns the stored block. Never raises -- recording is bookkeeping, and losing
    it must not fail an apply that has already written rows to the tenant.
    """
    try:
        fingerprint = outcome_fingerprint(
            created=created, updated=updated, quarantined=quarantined, status=status
        )
        previous = _progress_block(bundle, from_db=True)
        repeated = previous.get("fingerprint") == fingerprint
        made_rows = int(created or 0) > 0
        streak = (
            int(previous.get("no_progress_streak") or 0) + 1
            if (repeated and not made_rows)
            else 0
        )
        block = {
            "fingerprint": fingerprint,
            "no_progress_streak": streak,
            "last_created": int(created or 0),
            "last_updated": int(updated or 0),
            "last_quarantined": int(quarantined or 0),
            "last_status": str(status or ""),
        }
        _save_block(bundle, block)
        if streak >= no_progress_limit():
            logger.warning(
                "migration_cloud.apply_progress_guard: bundle %s has produced the "
                "identical result %s times in a row (created=%s updated=%s "
                "quarantined=%s) — automatic re-apply is now refused. An operator "
                "repair re-arms it.",
                getattr(bundle, "pk", "?"),
                streak,
                created,
                updated,
                quarantined,
            )
        return block
    except Exception:  # noqa: BLE001 — bookkeeping must never fail a written apply
        logger.debug(
            "apply_progress_guard: record failed bundle=%s",
            getattr(bundle, "pk", "?"),
            exc_info=True,
        )
        return {}


def reset_apply_progress(bundle) -> None:
    """Re-arm the budget. Called when a human deliberately asks for another go."""
    try:
        _save_block(bundle, {})
    except Exception:  # noqa: BLE001
        logger.debug(
            "apply_progress_guard: reset failed bundle=%s",
            getattr(bundle, "pk", "?"),
            exc_info=True,
        )


def livelock_reason(bundle) -> str:
    """Operator-facing explanation. Empty string when not livelocked.

    A silent refusal would be its own bug -- the caller is told "queued" and
    nothing happens, which is precisely the "Repair does nothing" complaint this
    subsystem already carries scar tissue for.
    """
    if not apply_is_livelocked(bundle):
        return ""
    block = _progress_block(bundle)
    return (
        "This import has been re-run {n} times with an identical result each time "
        "({c} created, {u} updated, {q} held for review), so it is not making "
        "progress and automatic retries have been stopped. The held records need "
        "a decision before another import can change anything."
    ).format(
        n=no_progress_streak(bundle),
        c=block.get("last_created", 0),
        u=block.get("last_updated", 0),
        q=block.get("last_quarantined", 0),
    )


__all__ = [
    "APPLY_PROGRESS_KEY",
    "DEFAULT_NO_PROGRESS_LIMIT",
    "apply_is_livelocked",
    "livelock_reason",
    "no_progress_limit",
    "no_progress_streak",
    "outcome_fingerprint",
    "record_apply_outcome",
    "reset_apply_progress",
]
