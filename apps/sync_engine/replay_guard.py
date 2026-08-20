"""Bundle replay defence: a signature says WHO built this, never that it is new.

THE GAP. Every delta bundle is HMAC-signed over HTTPS with a bearer edge credential.
That authenticates the builder and protects the bytes in flight. It says nothing about
whether this is the FIRST time the receiver has been handed them. Anyone who can obtain
a bundle - a LAN data-mule USB stick, a logging proxy, a backup of the box's spool
directory, an operator with the file - can present the identical bytes again later and
the signature will verify perfectly, every time.

WHY IT MATTERS EVEN THOUGH APPLY IS IDEMPOTENT. For a plain field update a replay is
merely wasteful. It is not harmless for anything whose meaning depends on WHEN it
arrived:

  * a bundle captured before a row was deleted RESURRECTS that row - the payload predates
    the tombstone, so the burial does not dominate it;
  * a bundle captured before a human resolved a conflict re-applies the value they chose
    against;
  * replaying a large bundle repeatedly is a cheap way to keep a metered link saturated
    and a box permanently behind.

THE MECHANISM. Every bundle carries a random ``nonce`` inside its SIGNED header, so it
cannot be rewritten to disguise a captured bundle as a fresh one. This module records
each accepted nonce per school and refuses one it has already seen. A sender too old to
emit a nonce falls back to the payload digest, so an un-updated appliance keeps working
and is still protected against a byte-identical replay.

The nonce is regenerated on every BUILD, not per row set. That distinction is what keeps
an honest retry working: a push that times out after the far side applied it is rebuilt
with a fresh nonce on the next cycle and accepted (then applied idempotently), while
replaying the captured bytes is refused.

THE WINDOW IS THE GUARANTEE. Receipts are pruned to
``RMC_SYNC_BUNDLE_REPLAY_WINDOW_SECONDS``, so protection reaches exactly that far back -
which is why a bundle whose ``exported_at`` is older than the window is REFUSED rather
than accepted with the protection quietly lapsed. That also bounds how badly a box's
clock may drift before an operator has to see it, which is a diagnosis worth forcing.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_DEFAULT_REPLAY_WINDOW_SECONDS = 7 * 24 * 3600  # magic-number-allow: replay window (7 days)
# A bundle stamped in the FUTURE is a clock problem, not an attack, and appliances
# without an RTC come up with wrong clocks routinely. Tolerated generously, then refused
# with a message that names the clock rather than blaming the payload.
_FUTURE_TOLERANCE_SECONDS = 24 * 3600  # magic-number-allow: clock-skew tolerance (1 day)


def replay_window_seconds() -> int:
    try:
        return max(
            60,
            int(
                getattr(
                    settings,
                    "RMC_SYNC_BUNDLE_REPLAY_WINDOW_SECONDS",
                    _DEFAULT_REPLAY_WINDOW_SECONDS,
                )
            ),
        )
    except (TypeError, ValueError):
        return _DEFAULT_REPLAY_WINDOW_SECONDS


def replay_defence_enabled() -> bool:
    """``RMC_SYNC_BUNDLE_REPLAY_DEFENCE=0`` disables. On by default."""
    return bool(getattr(settings, "RMC_SYNC_BUNDLE_REPLAY_DEFENCE", True))


def check_bundle_freshness(header: dict, *, now=None) -> str:
    """``""`` when the bundle is inside the window, else the error code to refuse with.

    Split out from :func:`register_bundle` so the age rule can be reasoned about (and
    tested) without a database.
    """
    window = replay_window_seconds()
    try:
        exported_at = int(header.get("exported_at") or 0)
    except (TypeError, ValueError):
        return "invalid_exported_at"
    if not exported_at:
        # A sender that stamps nothing cannot be aged. The nonce still protects it.
        return ""
    current = int(now if now is not None else time.time())
    if exported_at > current + _FUTURE_TOLERANCE_SECONDS:
        return "bundle_clock_ahead"
    if exported_at < current - window:
        return "bundle_expired"
    return ""


def register_bundle(school, collected: dict, *, direction: str = "", row_count: int = 0) -> str:
    """Record this bundle as seen. ``""`` to accept, otherwise the refusal code.

    ``collected`` is the dict :func:`apps.sync_engine.delta_bundle.verify_and_parse_bundle`
    fills in - it holds the VERIFIED header and the payload digest, so the nonce read here
    is one the signature already covered.

    An EMPTY bundle is not recorded. A bundle with no rows applies nothing, so replaying
    it changes nothing, and at a 20-second cadence the overwhelmingly common bundle is the
    empty one - recording those would fill the table with rows that protect against
    nothing.

    Never raises. If the receipt cannot be written the bundle is ACCEPTED: refusing real
    data because a defensive bookkeeping table is unavailable would turn a hardening
    measure into an outage. The failure is logged at warning level.
    """
    from apps.sync_engine.models import SyncBundleReceipt

    if not replay_defence_enabled() or school is None:
        return ""
    if row_count <= 0:
        return ""
    header = (collected or {}).get("header") or {}
    stale = check_bundle_freshness(header)
    if stale:
        return stale
    nonce = str(header.get("nonce") or "").strip()[:64]
    if not nonce:
        # Pre-nonce sender: the payload digest is a weaker but real substitute. It cannot
        # distinguish two genuinely identical rebuilds, which is precisely why new senders
        # emit an explicit nonce instead of relying on this.
        nonce = str((collected or {}).get("payload_digest") or "")[:64]
    if not nonce:
        return ""
    try:
        _obj, created = SyncBundleReceipt.objects.get_or_create(
            school=school,
            nonce=nonce,
            defaults={
                "row_count": int(row_count or 0),
                "direction": (direction or "")[:16],
            },
        )
    except Exception:  # noqa: BLE001 - see docstring: fail OPEN, loudly
        logger.warning("could not record a sync bundle receipt; accepting", exc_info=True)
        return ""
    if not created:
        return "bundle_replayed"
    prune_receipts(school)
    return ""


def prune_receipts(school=None) -> int:
    """Drop receipts past the replay window. Never raises."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.sync_engine.models import SyncBundleReceipt

    cutoff = timezone.now() - timedelta(seconds=replay_window_seconds())
    try:
        # tenant-isolation-allow: retention-sweep-is-intentionally-all-schools-when-no-school-given
        qs = SyncBundleReceipt.objects.filter(received_at__lt=cutoff)
        if school is not None:
            qs = qs.filter(school=school)
        return qs.delete()[0]
    except Exception:  # noqa: BLE001
        logger.debug("receipt prune failed", exc_info=True)
        return 0


__all__ = [
    "check_bundle_freshness",
    "prune_receipts",
    "register_bundle",
    "replay_defence_enabled",
    "replay_window_seconds",
]
