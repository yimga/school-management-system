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

When sentry_sdk isn't installed or SENTRY_DSN is unset, the decorator is a
no-op so test envs don't pull in the SDK.
"""

from __future__ import annotations

import functools
from typing import Callable


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
