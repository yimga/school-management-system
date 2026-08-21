"""Is edge<->cloud sync live on THIS deployment? One answer, one place.

WHY THIS EXISTS. ``RMC_EDGE_SYNC_ENABLED`` is an environment variable in
``deploy/selfhost/.env`` on the host. Pairing was built so that adopting a box needs
nothing but a code on a screen and an admin clicking approve — and then the box still
would not sync, because that env var was off and nobody told the installer to go and
edit a file they cannot see from the pairing screen. The credential was right, the
address was right, and the box sat there doing nothing. That is precisely the class of
silent misconfiguration the pairing work exists to end, so the flag cannot stay the
only answer.

THE RULE. Sync is live when EITHER:

  1. ``RMC_EDGE_SYNC_ENABLED`` is set — unchanged, still the explicit switch, and
     still the only thing that can turn sync on where no pairing has happened; or
  2. this deployment is a sovereign box AND it holds a durable pairing binding.

Condition 2 is not a weakening. A binding is written by exactly one thing:
:func:`edge_binding.save_binding`, called when the cloud handed this box a credential
because a signed-in administrator of that school approved it by name. That is a
STRONGER authorisation signal than an env var typed by whoever last touched the host,
and it is auditable — ``EdgePairingRequest.approved_by`` records who.

WHY THE SOVEREIGN-BOX CONDITION. ``EdgeCloudBinding`` lives in a SHARED app, so the
table also exists on the cloud. Nothing on the cloud ever writes to it — only
``pairing_client.poll()`` does, and that runs on a box — but "nothing writes it"
is an argument, and the deployment-shape check is a fact. A cloud tenant cannot be
switched into edge-sync behaviour by a row appearing in a table.

COST. This is read on the request path (the autosync middleware) and on every
scheduler scan, so the answer is memoised per process for a few seconds and shared
across processes through the cache. Pairing and unpairing bust it explicitly, so the
box starts syncing within one tick of being adopted rather than at the next restart.
"""
from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Short enough that a worker which never saw the explicit bust (a different gunicorn
# process, a Celery worker) still converges quickly; long enough that the steady state
# costs no database work.
_MEMO_TTL_SECONDS = 15
_CACHE_KEY = "rmc:edge:sync_enabled"
_CACHE_TTL_SECONDS = 30

_memo_lock = threading.Lock()
_memo_value: bool | None = None
_memo_stamped_at: float = 0.0


def env_flag_enabled() -> bool:
    """The original switch, unchanged. Useful on its own for diagnostics."""
    return bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False))


def is_sovereign_box() -> bool:
    """A single-school appliance rather than a multi-tenant cloud deployment."""
    if bool(getattr(settings, "SINGLE_TENANT", False)):
        return True
    return not bool(getattr(settings, "USE_DJANGO_TENANTS", True))


def _paired_uncached() -> bool:
    """Does a durable binding with a usable credential exist? Never raises."""
    try:
        from apps.sync_engine import edge_binding

        binding = edge_binding._binding()  # noqa: SLF001 — same package, one row
        if binding is None:
            return False
        return bool(binding.operator_base and binding.credential)
    except Exception:  # noqa: BLE001 — no table yet, no DB, apps not ready
        logger.debug("edge_enabled: binding lookup unavailable", exc_info=True)
        return False


def edge_sync_enabled() -> bool:
    """True when this deployment should actually push to / pull from a cloud."""
    if env_flag_enabled():
        return True
    if not is_sovereign_box():
        return False

    # Inert under the test runner, for the same reason the binding memo is: a
    # process-global answer with a 15s TTL outlives an individual test, so one test
    # that runs with no binding decides the answer for the next test that writes one.
    # That produced a failure visible ONLY in the full-suite run and not in isolation
    # — the worst kind to chase — so the cache is simply not in play under tests.
    if getattr(settings, "RUNNING_TESTS", False):
        return _paired_uncached()

    global _memo_value, _memo_stamped_at
    now = time.monotonic()
    with _memo_lock:
        if _memo_value is not None and (now - _memo_stamped_at) < _MEMO_TTL_SECONDS:
            return _memo_value

    value: bool | None = None
    try:
        from django.core.cache import cache

        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            value = bool(cached)
    except Exception:  # noqa: BLE001 — a cache outage must not decide this
        logger.debug("edge_enabled: cache read failed", exc_info=True)

    if value is None:
        value = _paired_uncached()
        try:
            from django.core.cache import cache

            cache.set(_CACHE_KEY, value, _CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.debug("edge_enabled: cache write failed", exc_info=True)

    with _memo_lock:
        _memo_value = value
        _memo_stamped_at = now
    return value


def invalidate() -> None:
    """Forget the memo. Called when a box is paired or unpaired.

    Without this a box would keep answering "not an edge box" for up to the memo TTL
    after being adopted, which is a confusing few seconds on the one screen an
    installer is actually watching.
    """
    global _memo_value, _memo_stamped_at
    with _memo_lock:
        _memo_value = None
        _memo_stamped_at = 0.0
    try:
        from apps.sync_engine.edge_binding import _forget_binding_memo

        # One call, one meaning: "forget everything cached about this box's pairing".
        # Leaving the binding memo behind would let this answer False from a row that
        # no longer exists (or True from one that does not yet).
        _forget_binding_memo()
    except Exception:  # noqa: BLE001
        logger.debug("edge_enabled: could not forget the binding memo", exc_info=True)
    try:
        from django.core.cache import cache

        cache.delete(_CACHE_KEY)
    except Exception:  # noqa: BLE001
        logger.debug("edge_enabled: cache delete failed", exc_info=True)


def why() -> dict:
    """Explain the answer, for the readiness command and the Sync Center."""
    env = env_flag_enabled()
    sovereign = is_sovereign_box()
    paired = _paired_uncached() if sovereign else False
    return {
        "enabled": bool(env or (sovereign and paired)),
        "env_flag": env,
        "sovereign_box": sovereign,
        "paired": paired,
        "reason": (
            "RMC_EDGE_SYNC_ENABLED is set"
            if env
            else "this box is paired to a cloud tenant"
            if (sovereign and paired)
            else "not a sovereign box"
            if not sovereign
            else "no pairing binding and RMC_EDGE_SYNC_ENABLED is off"
        ),
    }


__all__ = [
    "edge_sync_enabled",
    "env_flag_enabled",
    "invalidate",
    "is_sovereign_box",
    "why",
]
