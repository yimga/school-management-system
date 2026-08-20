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


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


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


def edge_sync_tick_seconds() -> int:
    """How often the dispatcher should CONSIDER a sync — not how often one runs.

    Registering the job at a slow interval put a hard floor under how quickly the box
    could ever react: with a 180s registration, a wake raised one second after a tick
    still waited ~179s. So the dispatcher now ticks at this short cadence and
    :func:`run_edge_sync_now` decides — a tick that is not due returns in microseconds
    without touching the network or the corpus, so a fast tick is close to free.

    Floored at :data:`cadence.MIN_INTERVAL_SECONDS`, and never slower than an explicit
    operator pin (pinning 600s should not make the box tick every 5s to do nothing).
    """
    from apps.sync_engine import cadence

    tick = max(cadence.MIN_INTERVAL_SECONDS, _env_int("RMC_EDGE_SYNC_TICK_SECONDS", 5))
    pin = cadence.pinned_interval_seconds()
    return min(tick, pin) if pin else tick


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


def run_edge_sync_now(*, mode: str = "live", force: bool = False, trigger: str = "") -> dict:
    """Run ONE automatic edge<->cloud sync cycle for the box's school.

    Gated by ``RMC_EDGE_SYNC_ENABLED`` and never-raising. Returns a small result
    dict; the transport work + the single EdgeSyncRun record happen inside
    :func:`sync_runner.run_sync_cycle`.

    ``mode="live"`` pushes up then pulls down and applies; ``mode="dry"`` is a
    no-write connectivity probe.

    CADENCE. The periodic dispatcher now ticks this entry FAST (see
    ``platform_runtime.periodic``) and the decision about whether a full cycle is
    actually warranted lives here, in :mod:`apps.sync_engine.cadence` — one place, shared
    by every trigger. ``force=True`` bypasses the gate; that is what the operator's
    "Sync now" button, the boot entrypoint and the ``edge_autosync`` command pass, because
    a human or a boot asked explicitly and must never be answered with "not due yet".

    The cheap reachability probe runs on every call. It NEVER blocks the cycle — a probe
    that wrongly reports offline (a TCP-blocking middlebox, an HTTP-only proxy) must not
    be able to stop syncing. Its only jobs are to raise a wake the instant the network
    comes back, and to make the status surface honest.
    """
    if not _edge_sync_enabled():
        return {"enabled": False, "ran": False, "reason": "RMC_EDGE_SYNC_ENABLED is off"}

    from apps.sync_engine import cadence, connectivity

    # Cheap, never-raising, and the thing that cancels backoff the moment the link is
    # back. Deliberately before the due-check so a restored network is seen immediately.
    try:
        link = connectivity.check()
    except Exception:  # noqa: BLE001 — a probe must never break a scheduler tick
        logger.debug("connectivity probe failed", exc_info=True)
        link = {}

    # Resolve the school BEFORE the cadence gate. Cheap (one local query) and its failure
    # is a PERMANENT configuration error, so answering a misconfigured box with
    # "not due for 44s (steady)" hides the only thing its operator needed to be told.
    # Reported regardless of cadence, and without burning cadence state on a condition
    # that can never succeed.
    try:
        school = resolve_edge_school()
    except Exception:  # noqa: BLE001 - resolution must never crash a scheduler tick
        logger.debug("resolve_edge_school failed", exc_info=True)
        school = None
    if school is None:
        return {
            "enabled": True,
            "ran": False,
            "reason": "no unambiguous edge school to sync (set RMC_EDGE_SCHOOL_SLUG)",
            "online": link.get("online"),
        }

    if not force:
        due, why = cadence.due_now()
        if not due:
            return {
                "enabled": True,
                "ran": False,
                "skipped": True,
                "reason": why,
                "online": link.get("online"),
            }

        # The box is due, but the cheap probe says the operator is unreachable. Building
        # and signing a bundle for a socket that cannot open is the single most wasteful
        # thing an offline box can do, so skip the expensive part and let the probe keep
        # watching — a restored link raises a wake and the next tick runs immediately.
        #
        # BOUNDED, because the probe is a network check and can be wrong: after
        # MAX_CONSECUTIVE_PROBE_SKIPS vetoes we run a real cycle regardless, so a
        # middlebox that blocks TCP while HTTP still works costs a few skipped ticks
        # rather than silently muting sync forever. A pending wake is never skipped.
        # `link["host"]` must be truthy. With no operator base configured, check() reports
        # online=False with host="" - that is a CONFIGURATION error, not a network one, and
        # vetoing on it would suppress up to MAX_CONSECUTIVE_PROBE_SKIPS cycles while
        # telling the operator "operator unreachable", sending them to check their internet
        # instead of their settings. Let the cycle run: it fails on the same missing
        # setting and names it.
        if (
            link.get("online") is False
            and link.get("host")
            and not cadence.pending_wake()
            and cadence.probe_skips() < cadence.MAX_CONSECUTIVE_PROBE_SKIPS
        ):
            skips = cadence.note_probe_skip()
            cadence.schedule_next()
            return {
                "enabled": True,
                "ran": False,
                "skipped": True,
                "online": False,
                "probe_skips": skips,
                "reason": (
                    f"operator unreachable ({link.get('host') or 'no host'}); "
                    f"skipped the cycle to stay cheap ({skips}/"
                    f"{cadence.MAX_CONSECUTIVE_PROBE_SKIPS})"
                ),
            }

    # Committed to running: only now is the wake spent, so a tick that bailed above
    # (not due, operator unreachable) leaves it standing for the tick that can use it.
    wake_reason = cadence.consume_wake()

    from apps.sync_engine import sync_runner

    result = sync_runner.run_sync_cycle(school, mode=mode)
    result.setdefault("ran", True)
    result["trigger"] = (trigger or ("wake" if wake_reason else "cadence")).strip()[:60]
    result["online"] = link.get("online")

    # A dry run writes nothing and proves nothing about throughput, so it must not be
    # allowed to drive the box HOT or to clear a real backoff.
    if mode == "live":
        result["cadence"] = cadence.record_cycle(result)
    return result


__all__ = [
    "edge_sync_interval_seconds",
    "edge_sync_tick_seconds",
    "resolve_edge_school",
    "run_edge_sync_now",
]
