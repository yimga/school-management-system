"""
Pass 11.C: reusable sentry_sdk transaction wrappers for the 3 hottest views.

Sentry's Django integration already captures every request as a transaction,
but the default sampling rate (5%) plus generic op="http.server" makes hot
paths hard to find on the perf board. This module exposes a small decorator
that promotes a view to op="<custom>" with a dedicated name, so dashboards
can drill into attendance / grade-publish / parent-dashboard latency without
sifting the whole web tier.

Usage:

    @trace_view("attendance.submit")
    def submit_attendance(request, ...): ...

For non-view code paths (background tasks, service-layer functions),
use the lower-level :func:`start_named_transaction` /
:func:`finish_transaction` helpers.

When sentry_sdk isn't installed or SENTRY_DSN is unset, every helper here
becomes a no-op so test envs don't pull in the SDK.
"""

from __future__ import annotations

import functools
from typing import Any, Callable


def start_named_transaction(name: str, *, op: str = "task.hot_path", **tags: Any):
    """Start a named Sentry transaction. Returns the transaction object
    (or ``None`` when sentry_sdk is unavailable). Always pair with
    :func:`finish_transaction`.

    For request-handling code, prefer :func:`trace_view`. This helper
    exists for tasks, service-layer functions, and outbox processors —
    anywhere there is no `request` to bind to.
    """
    try:
        import sentry_sdk
    except ImportError:
        return None
    try:
        txn = sentry_sdk.start_transaction(op=op, name=name)
        for key, value in tags.items():
            try:
                txn.set_tag(key, value)
            except Exception:  # noqa: BLE001 - telemetry never blocks
                pass
        return txn
    except Exception:  # noqa: BLE001
        return None


def set_transaction_status(txn, status: str) -> None:
    if txn is None:
        return
    try:
        txn.set_status(status)
    except Exception:  # noqa: BLE001
        pass


def finish_transaction(txn) -> None:
    if txn is None:
        return
    try:
        txn.finish()
    except Exception:  # noqa: BLE001
        pass


def set_tags(**tags: Any) -> None:
    """Tag the current Sentry scope with arbitrary key/value pairs.

    Used by middleware (e.g. tenant tagging) so app code never imports
    ``sentry_sdk`` directly. No-op when the SDK isn't available.
    """
    if not tags:
        return
    try:
        import sentry_sdk
    except ImportError:
        return
    for key, value in tags.items():
        try:
            sentry_sdk.set_tag(key, "" if value is None else str(value))
        except Exception:  # noqa: BLE001 - telemetry never blocks
            pass


def trace_view(name: str, op: str = "view.hot_path") -> Callable:
    """
    Wrap a view in a sentry_sdk transaction. `name` is the transaction name
    (shown on the perf board); `op` is the operation type for grouping.
    """

    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(*args, **kwargs):
            try:
                import sentry_sdk
            except ImportError:
                return view_func(*args, **kwargs)
            transaction = sentry_sdk.start_transaction(op=op, name=name)
            try:
                return view_func(*args, **kwargs)
            except Exception:
                try:
                    transaction.set_status("internal_error")
                except Exception:  # noqa: BLE001 - never block on telemetry
                    pass
                raise
            finally:
                try:
                    transaction.finish()
                except Exception:  # noqa: BLE001
                    pass

        return wrapper

    return decorator
