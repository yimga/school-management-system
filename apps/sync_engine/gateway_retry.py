"""Retry a cloud request that failed at the PROXY rather than in the application.

WHY. Measured against the production cloud on 2026-08-20 at 21:07 UTC, with no deploy
in flight, every single path returned 502 with ``x-render-routing: dynamic-paid-error``:

    502  /static/js/service-worker.js
    502  /healthz/
    502  /
    502  /api/nonexistent-route-xyz/     <- a route that does not exist

Sixty seconds later all of them served correctly, but slowly on first touch — the login
page took 8.0s, an unknown path 12.4s. A static asset cannot 502 from schema drift and a
nonexistent route cannot 502 from application code, so this is the service being COLD,
not a tenant being broken.

That distinction is the whole point. A box syncing on a cadence hits the cold cloud, takes
a 502 on its first request, and records a failure. A human then opens a browser — which
warms the service — and sees a perfectly healthy site. The asymmetry can hide a
permanently failing sync indefinitely, and it is exactly what happened here.

WHAT THIS DOES NOT DO. 502/503/504 only. A 4xx is a decision the cloud made and must be
surfaced immediately: retrying a 401 hammers an endpoint with a credential that will never
work, and retrying a 404 hides a path bug behind latency. A connectivity failure
(``URLError``/``OSError``) is not handled here either — the caller already queues and
retries those, and a box that is genuinely offline must not spend its cycle sleeping.

Retries are bounded and the total added wall-clock is capped, because a sync cycle that
never returns is worse than one that fails and tries again on the next tick.
"""
from __future__ import annotations

import os
import time
from typing import Callable

# Gateway-level failures: the proxy answered, the application did not. Every one of these
# is plausibly transient, which is what separates them from a 4xx.
GATEWAY_STATUSES: tuple[int, ...] = (502, 503, 504)


def _float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def gateway_retry_attempts() -> int:
    """Total attempts including the first. 1 disables retrying entirely."""
    return _int_env("RMC_SYNC_GATEWAY_RETRY_ATTEMPTS", 3)


def gateway_retry_delays() -> list[float]:
    """Backoff before attempts 2..N.

    5s then 20s by default: a cold container is usually answering again inside 30
    seconds, and 25s of added worst-case latency is affordable against a sync interval
    measured in minutes. Tunable because a satellite link and a LAN are not the same
    problem.
    """
    base = _float_env("RMC_SYNC_GATEWAY_RETRY_BASE_SECONDS", 5.0)
    attempts = gateway_retry_attempts()
    # Geometric, not linear: the first retry covers a brief blip, the last covers a real
    # cold start, without a long tail of pointless mid-range waits.
    return [base * (4.0**i) for i in range(max(0, attempts - 1))]


def is_gateway_error(status: object) -> bool:
    """True for a proxy-level failure worth retrying."""
    try:
        return int(status) in GATEWAY_STATUSES
    except (TypeError, ValueError):
        return False


def call_with_gateway_retry(
    do_request: Callable[[], tuple],
    *,
    attempts: int | None = None,
    delays: list[float] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, int, float], None] | None = None,
) -> tuple:
    """Run ``do_request`` until it returns a non-gateway status or attempts run out.

    ``do_request`` must return ``(status, body)`` and must NOT raise for HTTP status —
    that is the existing contract in ``edge_outbox``/``file_sync``, where a 4xx/5xx is a
    returned response and only a connectivity failure propagates. Connectivity failures
    are deliberately allowed to propagate through this wrapper unchanged.

    Returns the LAST response, so a cloud that is genuinely down still surfaces its 502
    to the caller rather than being silently converted into something else.
    """
    total = gateway_retry_attempts() if attempts is None else max(1, int(attempts))
    waits = gateway_retry_delays() if delays is None else list(delays)

    status, body = do_request()
    for index in range(1, total):
        if not is_gateway_error(status):
            return status, body
        wait = waits[index - 1] if index - 1 < len(waits) else (waits[-1] if waits else 0.0)
        if on_retry is not None:
            try:
                on_retry(index, total, wait)
            except Exception:  # noqa: BLE001 — telemetry must never break transport
                pass
        if wait > 0:
            sleep(wait)
        status, body = do_request()
    return status, body


def gateway_error_hint(status: object) -> str:
    """One sentence an operator can act on, for logs and the Sync Center.

    Deliberately does NOT blame the box's configuration. Every message in this product
    used to point at ``RMC_EDGE_OPERATOR_BASE`` for a 502, and that setting has never
    once been the cause.
    """
    if not is_gateway_error(status):
        return ""
    return (
        f"The cloud's proxy answered HTTP {status} but its application did not. This is "
        "not a box-side fault and the operator base is not the cause. Two things produce "
        "it: the cloud service being cold (it recovers within a minute — this request was "
        "already retried), or one tenant schema missing a column, which makes every "
        "bundle build raise. On the CLOUD run: python manage.py "
        "check_edge_sync_deploy_readiness, then check the application logs."
    )
