"""Resolve pushes whose fate the box never learned.

Two functions, both called from ``sync_runner``'s push phase:

  * :func:`record_ambiguous_push` — after a push fails in a way that means the cloud
    MIGHT have applied it.
  * :func:`resolve_pending` — at the start of the next push phase, before rebuilding
    anything. Asks the cloud, advances the cursor over anything it confirms, and drops
    the question either way.

WHAT COUNTS AS AMBIGUOUS, and why the distinction is the whole feature. A 400 or a 403
is a decision: the cloud answered, and the answer was no. Nothing was applied, and
re-shipping is exactly right. A read timeout, a connection reset, or a 502/503/504 is
NOT a decision — the request may have been fully processed and only the reply lost. Only
the second kind is worth a follow-up question, and treating the first kind as ambiguous
would have the box asking about bundles that were explicitly rejected.

Everything here is best-effort. If the lookup fails, is unreachable, or answers
"unknown", the box does what it did before this module existed: rebuild and re-ship.
That path is correct — ``export_delta_bundle`` regenerates the nonce per build, so a
rebuilt bundle is new to the replay guard and the apply is idempotent. This is a
bandwidth optimisation on a link that has just proven unreliable, never a correctness
mechanism, and it must never be able to BLOCK a push.
"""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15

# Gateway/proxy statuses that mean "the answer was lost", not "the answer was no".
AMBIGUOUS_STATUSES = frozenset({0, 502, 503, 504, 408, 522, 524})


def is_ambiguous_failure(status: int) -> bool:
    """True when the cloud may have applied the bundle despite the failure."""
    return int(status or 0) in AMBIGUOUS_STATUSES


def record_ambiguous_push(
    school, *, data: bytes, high_water: str = "", row_count: int = 0, failure: str = ""
) -> None:
    """Remember a bundle whose outcome is unknown. Never raises."""
    try:
        from apps.sync_engine.delta_bundle import bundle_nonce
        from apps.sync_engine.models_pairing import PendingPushConfirmation

        nonce = bundle_nonce(data)
        if not nonce:
            return
        built_at = 0
        try:
            header = json.loads(data.decode("utf-8").splitlines()[0])
            built_at = int(header.get("exported_at") or 0)
        except (ValueError, IndexError, UnicodeDecodeError, AttributeError):
            built_at = 0
        PendingPushConfirmation.objects.update_or_create(  # tenant-isolation-allow: explicitly-scoped-to-the-school-being-synced
            school=school,
            nonce=nonce,
            defaults={
                "high_water": (high_water or "")[:64],
                "row_count": int(row_count or 0),
                "built_at": built_at,
                "failure": (failure or "")[:120],
            },
        )
        logger.info(
            "push_confirmation: recorded ambiguous push nonce=%s rows=%s (%s)",
            nonce[:12],
            row_count,
            failure,
        )
    except Exception:  # noqa: BLE001 — bookkeeping must never break the sync cycle
        logger.debug("push_confirmation: could not record", exc_info=True)


def _ask(base: str, token: str, nonce: str, built_at: int) -> dict:
    """One receipt lookup. Returns {} when the question could not be asked."""
    from apps.sync_engine.cloud_endpoints import cloud_endpoint

    url = (
        f"{cloud_endpoint(base, 'api:sync-bundle-receipt')}"
        f"?nonce={urllib.parse.quote(nonce)}&built_at={int(built_at or 0)}"
    )
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8") or "{}")
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        socket.timeout,
        OSError,
        ValueError,
    ):
        return {}


def resolve_pending(school, *, base: str, token: str, set_cursor=None) -> dict:
    """Ask about every unresolved push for ``school``.

    Returns ``{"confirmed": n, "unconfirmed": n, "asked": n}``. ``set_cursor`` is
    called as ``set_cursor(high_water)`` for each confirmed bundle that carried one,
    so this module never imports the cursor machinery.

    Never raises.
    """
    result = {"confirmed": 0, "unconfirmed": 0, "asked": 0}
    if not base or not token:
        return result
    try:
        from apps.sync_engine.models_pairing import PendingPushConfirmation

        pending = list(
            PendingPushConfirmation.objects.filter(  # tenant-isolation-allow: explicitly-scoped-to-the-school-being-synced
                school=school
            )[:20]
        )
    except Exception:  # noqa: BLE001
        logger.debug("push_confirmation: could not load pending", exc_info=True)
        return result

    for row in pending:
        answer = _ask(base, token, row.nonce, row.built_at)
        result["asked"] += 1
        if not answer.get("ok"):
            # Could not ask. Leave the row for next cycle; the ordinary re-ship still
            # happens meanwhile, so nothing stalls waiting on this.
            row.attempts = (row.attempts or 0) + 1
            try:
                row.save(update_fields=["attempts"])
            except Exception:  # noqa: BLE001
                pass
            result["unconfirmed"] += 1
            continue
        if answer.get("seen"):
            logger.info(
                "push_confirmation: cloud already had nonce=%s (%s rows) — "
                "advancing instead of re-shipping",
                row.nonce[:12],
                row.row_count,
            )
            if set_cursor is not None and row.high_water:
                try:
                    set_cursor(row.high_water)
                except Exception:  # noqa: BLE001
                    logger.debug("push_confirmation: cursor advance failed", exc_info=True)
            result["confirmed"] += 1
        else:
            # Either a confident "no", or "unknown" (pruned out of the replay window).
            # Both lead to the same safe action: let the ordinary re-ship happen.
            result["unconfirmed"] += 1
        try:
            row.delete()
        except Exception:  # noqa: BLE001
            logger.debug("push_confirmation: could not clear row", exc_info=True)
    return result


__all__ = [
    "AMBIGUOUS_STATUSES",
    "is_ambiguous_failure",
    "record_ambiguous_push",
    "resolve_pending",
]
