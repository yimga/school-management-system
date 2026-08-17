"""Zero-config automatic edge<->cloud sync: resolve the box's school + run one cycle.

The single, gated, never-raising entry that EVERY automatic trigger converges on —
the in-process periodic scheduler (the ``/health/`` tick), the Celery-beat task, the
boot-time entrypoint reconcile, and the optional on-connectivity host hook. All of
them call :func:`run_edge_sync_now`, which:

  * is a HARD no-op unless ``settings.RMC_EDGE_SYNC_ENABLED`` — so every ordinary
    cloud tenant is untouched (the flag is set only on a sovereign edge box);
  * resolves the box's own school WITHOUT the operator passing a slug (an edge box
    serves exactly one school), so the automatic paths need no arguments;
  * delegates to the SAME never-raising :func:`sync_runner.run_sync_cycle` the
    "Sync now" button uses, recording exactly one EdgeSyncRun per attempt.

Because the underlying cycle is cursor-based and offline-safe, an attempt made while
the box is offline is a harmless no-op that leaves the cursors put and retries next
tick — which is exactly the "resync once the network is stable again" behaviour after
a power loss or an abrupt disconnect. The box therefore auto-syncs simply by being up
and having its ``/health/`` endpoint pinged; the first tick after the network returns
reconciles both directions.
"""
from __future__ import annotations

import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

# Default cadence for the automatic sync cycle. Short by design: an attempt while
# offline is a cheap no-op, so a tight cadence means the box reconciles within a
# couple of minutes of the network returning — with no host-level connectivity hook.
_DEFAULT_INTERVAL_SECONDS = 180  # magic-number-allow: default edge auto-sync interval (seconds)
_MIN_INTERVAL_SECONDS = 60  # floor so a misconfig can't hammer the cloud


def _edge_sync_enabled() -> bool:
    return bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False))


def edge_sync_interval_seconds() -> int:
    """How often the box attempts an automatic sync cycle (default 180s, floor 60s).

    Overridable via ``RMC_EDGE_SYNC_INTERVAL_SECONDS``.
    """
    raw = os.getenv("RMC_EDGE_SYNC_INTERVAL_SECONDS", "").strip()
    try:
        val = int(raw) if raw else _DEFAULT_INTERVAL_SECONDS
    except (TypeError, ValueError):
        val = _DEFAULT_INTERVAL_SECONDS
    return max(_MIN_INTERVAL_SECONDS, val)


def resolve_edge_school():
    """The single school this edge box serves, or ``None``.

    Resolution order:
      1. an explicit ``RMC_EDGE_SCHOOL_SLUG`` (wins if set), else
      2. the sole active school (an edge box serves exactly one).

    Ambiguous — no slug and 0 or >1 active schools — returns ``None`` so the caller
    no-ops instead of guessing which tenant to sync.
    """
    from apps.schools.models import School

    slug = (os.getenv("RMC_EDGE_SCHOOL_SLUG", "") or "").strip().lower()
    if slug:
        return School.objects.filter(slug=slug).first()
    # Pull two so we can distinguish "exactly one" from "more than one" cheaply.
    actives = list(School.objects.filter(is_active=True)[:2])
    if len(actives) == 1:
        return actives[0]
    return None


def run_edge_sync_now(*, mode: str = "live") -> dict:
    """Run ONE automatic edge<->cloud sync cycle for the box's school.

    Gated by ``RMC_EDGE_SYNC_ENABLED`` and never-raising. Returns a small result
    dict; the transport work + the single EdgeSyncRun record happen inside
    :func:`sync_runner.run_sync_cycle`.

    ``mode="live"`` pushes up then pulls down and applies; ``mode="dry"`` is a
    no-write connectivity probe.
    """
    if not _edge_sync_enabled():
        return {"enabled": False, "ran": False, "reason": "RMC_EDGE_SYNC_ENABLED is off"}
    try:
        school = resolve_edge_school()
    except Exception:  # noqa: BLE001 — resolution must never crash a scheduler tick
        logger.debug("resolve_edge_school failed", exc_info=True)
        school = None
    if school is None:
        return {
            "enabled": True,
            "ran": False,
            "reason": "no unambiguous edge school to sync (set RMC_EDGE_SCHOOL_SLUG)",
        }
    from apps.sync_engine import sync_runner

    result = sync_runner.run_sync_cycle(school, mode=mode)
    result.setdefault("ran", True)
    return result


__all__ = ["edge_sync_interval_seconds", "resolve_edge_school", "run_edge_sync_now"]
