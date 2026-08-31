"""G7: how far is this box's clock from the cloud's, and does anybody know?

Every cursor in this engine is a wall-clock ``updated_at``. ``get_sync_cursor_for_request``
says so plainly and buys back the two races it can with a 120-second overlap. What
nothing anywhere measured is the thing that overlap is denominated in: the box's clock
and the cloud's clock are two different clocks, and an appliance in a school with no
network time source drifts. A box 20 minutes FAST asks for rows "since" a moment the
cloud has not reached and pulls nothing while believing it is caught up; a box 20 minutes
SLOW re-pulls the same window forever. Neither shows up as an error anywhere — the sync
runs, reports success, and converges on the wrong thing.

The measurement costs a single header. HTTP requires ``Date`` on the response, so the
cloud has been telling every box its own time on every cycle since the first one; the box
simply threw it away. Reading it is free and needs no new endpoint, no NTP client and no
second round trip.

WHAT THIS IS NOT. It is not an alerting system and it does not correct anything. Slewing
a system clock from inside a Django process would be worse than the drift; and a cursor
that silently rewrote itself against a measured offset would be a second, undocumented
clock. This records the number, keeps the last reading where an operator can find it, and
makes a large one visible in the sync run's own message — where the operator is already
looking when a box seems stuck.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as _dt_timezone

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Default threshold: the same 120 seconds as ``RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS``,
#: and for the same reason rather than by coincidence. The overlap is the engine's whole
#: tolerance for wall-clock disagreement, so an offset at or beyond it has consumed the
#: entire safety margin the cursor design depends on. Once drift exceeds the overlap, a
#: row can fall behind the cursor and never be re-offered.
_DEFAULT_WARN_SECONDS = 120  # magic-number-allow: mirrors the cursor overlap default

_CACHE_KEY = "rmc:edge_sync:clock_offset:%s"
_CACHE_TTL_SECONDS = 30 * 24 * 3600  # magic-number-allow: last-reading retention (30d, seconds)


#: What the measurement can actually raise: an absent module, a Date header a proxy
#: rewrote into nonsense, a timestamp outside the platform's range, a cache backend that
#: is down. Named rather than blanket, for the same reason as in ``compression``: "a
#: diagnostic must never cost the box its data" is a promise, not a licence to swallow a
#: bug in the diagnostic itself.
_SOFT_FAILURES = (
    AttributeError,
    ImportError,
    LookupError,
    OSError,
    OverflowError,
    RuntimeError,
    TypeError,
    ValueError,
)


def warn_threshold_seconds() -> int:
    """Offset magnitude at or above which the run says so out loud.

    ``RMC_EDGE_SYNC_CLOCK_SKEW_WARN_SECONDS``, which ``config/settings.py`` DEFAULTS to
    ``RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS`` at load: the two numbers mean the same
    thing, so an operator who widens the overlap widens what counts as an alarming clock
    without having to know this second name exists. The overlap is read here only as a
    fallback for a deployment whose settings module predates the skew setting.
    """
    fallback = getattr(
        settings, "RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS", _DEFAULT_WARN_SECONDS
    )
    try:
        return max(
            1,
            int(
                getattr(settings, "RMC_EDGE_SYNC_CLOCK_SKEW_WARN_SECONDS", fallback)
                or _DEFAULT_WARN_SECONDS
            ),
        )
    except (TypeError, ValueError):
        return _DEFAULT_WARN_SECONDS


def parse_http_date(raw) -> datetime | None:
    """RFC 7231 ``Date`` header -> aware UTC datetime, or ``None``.

    Never raises. A header a proxy rewrote into something unparseable means "no
    measurement this cycle", which is strictly better than a wrong measurement.
    """
    if not raw:
        return None
    try:
        from django.utils.http import parse_http_date as _parse

        return datetime.fromtimestamp(_parse(str(raw).strip()), tz=_dt_timezone.utc)
    except _SOFT_FAILURES:
        logger.debug("unparseable Date header on a sync response", exc_info=True)
        return None


def measure(clock) -> dict | None:
    """Turn ``pull_bundle``'s ``collect["clock"]`` into a reading, or ``None``.

    Returns ``{"offset_seconds", "round_trip_seconds", "server_time", "local_time"}``.

    The offset is measured against the MIDPOINT of the round trip, not against the moment
    the body finished arriving. On a village link the response can be seconds old by the
    time it is read, and attributing that to the clock would report a skew that is really
    just latency — the exact false positive that would teach an operator to ignore this
    number. ``round_trip_seconds`` is carried alongside so the reading can be read with
    its own error bar: an offset smaller than the round trip is not evidence of anything.
    """
    if not isinstance(clock, dict):
        return None
    server_time = parse_http_date(clock.get("server_date"))
    if server_time is None:
        return None
    sent = clock.get("local_sent")
    received = clock.get("local_received")
    if not isinstance(received, datetime):
        received = timezone.now()
    if not isinstance(sent, datetime):
        sent = received
    if timezone.is_naive(sent):
        sent = timezone.make_aware(sent, timezone.get_current_timezone())
    if timezone.is_naive(received):
        received = timezone.make_aware(received, timezone.get_current_timezone())
    round_trip = max(0.0, (received - sent).total_seconds())
    local_time = sent + timedelta(seconds=round_trip / 2)
    return {
        "offset_seconds": round((local_time - server_time).total_seconds(), 3),
        "round_trip_seconds": round(round_trip, 3),
        "server_time": server_time,
        "local_time": local_time,
    }


def record(school, reading) -> dict | None:
    """Keep the reading where an operator can find it later. Returns it unchanged.

    Cached rather than given a table of its own: this app declares no models (see its
    README), a migration on fifteen live tenants to hold one float would be out of all
    proportion, and the durable record an operator actually reads is the note this
    produces on the ``EdgeSyncRun`` itself. The cache entry is the convenience copy for a
    surface that wants the latest number without parsing a message.
    """
    if not reading:
        return reading
    try:
        from django.core.cache import cache

        cache.set(
            _CACHE_KEY % getattr(school, "pk", school),
            {
                "offset_seconds": reading["offset_seconds"],
                "round_trip_seconds": reading["round_trip_seconds"],
                "observed_at": timezone.now().isoformat(),
            },
            _CACHE_TTL_SECONDS,
        )
    except _SOFT_FAILURES:
        logger.debug("could not store the clock offset reading", exc_info=True)
    return reading


def last_observed(school) -> dict | None:
    """The most recent reading for this school, or ``None`` if none is remembered."""
    try:
        from django.core.cache import cache

        return cache.get(_CACHE_KEY % getattr(school, "pk", school))
    except _SOFT_FAILURES:
        return None


def is_large(reading) -> bool:
    """Is this offset big enough that the cursor's safety margin is gone?"""
    if not reading:
        return False
    return abs(float(reading.get("offset_seconds") or 0)) >= warn_threshold_seconds()


def describe(reading) -> str:
    """One operator-readable sentence, or ``""`` when there is nothing to say.

    Only speaks up when the offset is large. A healthy box reports its offset in
    ``result["clock_offset_seconds"]`` and in the cache; putting a line about a two-second
    clock into every run message would bury the notes that matter.
    """
    if not is_large(reading):
        return ""
    offset = float(reading["offset_seconds"])
    direction = "AHEAD of" if offset > 0 else "BEHIND"
    return (
        f"WARNING: this box's clock is {abs(offset):.0f}s {direction} the cloud's "
        f"(round trip {float(reading.get('round_trip_seconds') or 0):.1f}s, threshold "
        f"{warn_threshold_seconds()}s). Sync cursors are wall-clock `updated_at` "
        f"positions compared across both sides, and the {warn_threshold_seconds()}s "
        "overlap that protects them is now smaller than the drift — rows can fall behind "
        "the cursor and never be re-offered. Set a time source on this box."
    )


def observe(school, clock) -> dict | None:
    """Measure, store, and hand back the reading. The one call a cycle needs."""
    reading = measure(clock)
    if reading is None:
        return None
    record(school, reading)
    if is_large(reading):
        logger.warning(
            "edge sync: clock offset %.1fs for school=%s (threshold %ss)",
            reading["offset_seconds"],
            getattr(school, "pk", None),
            warn_threshold_seconds(),
        )
    return reading


__all__ = [
    "describe",
    "is_large",
    "last_observed",
    "measure",
    "observe",
    "parse_http_date",
    "record",
    "warn_threshold_seconds",
]
