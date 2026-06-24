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

When sentry_sdk isn't installed or SENTRY_DSN is unset, SLO metrics still
record via :mod:`apps.observability.slo_metrics` — only Sentry spans are skipped.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable


@dataclass
class _TraceHandle:
    """Pairs a trace name + timer with an optional Sentry transaction."""

    name: str
    started_at: float
    sentry_txn: Any | None = None
    success: bool = field(default=True)


def _resolve_handle(txn_or_handle: Any | None) -> _TraceHandle | None:
    if txn_or_handle is None:
        return None
    if isinstance(txn_or_handle, _TraceHandle):
        return txn_or_handle
    name = getattr(txn_or_handle, "_rmc_trace_name", None)
    started = getattr(txn_or_handle, "_rmc_trace_started", None)
    if name and started is not None:
        return _TraceHandle(name=str(name), started_at=float(started), sentry_txn=txn_or_handle)
    return None


def start_named_transaction(name: str, *, op: str = "task.hot_path", **tags: Any):
    """Start a named Sentry transaction. Returns a :class:`_TraceHandle`.

    Always pair with :func:`finish_transaction`. The handle records SLO-aligned
    Prometheus metrics on finish even when Sentry is unavailable.
    """
    started = perf_counter()
    sentry_txn = None
    try:
        import sentry_sdk
    except ImportError:
        sentry_sdk = None  # type: ignore[assignment]
    if sentry_sdk is not None:
        try:
            sentry_txn = sentry_sdk.start_transaction(op=op, name=name)
            for key, value in tags.items():
                try:
                    sentry_txn.set_tag(key, value)
                except Exception:  # noqa: BLE001 - telemetry never blocks
                    pass
        except Exception:  # noqa: BLE001
            sentry_txn = None
    return _TraceHandle(name=name, started_at=started, sentry_txn=sentry_txn)


def set_transaction_status(txn_or_handle, status: str) -> None:
    handle = _resolve_handle(txn_or_handle)
    txn = handle.sentry_txn if handle is not None else txn_or_handle
    if handle is not None and status in ("internal_error", "unknown_error", "data_loss"):
        handle.success = False
    if txn is None:
        return
    try:
        txn.set_status(status)
    except Exception:  # noqa: BLE001
        pass


def finish_transaction(txn_or_handle, *, success: bool | None = None) -> None:
    handle = _resolve_handle(txn_or_handle)
    if handle is None:
        return
    if success is not None:
        handle.success = success
    duration = perf_counter() - handle.started_at
    try:
        from apps.observability.slo_metrics import record_traced_transaction

        record_traced_transaction(
            handle.name,
            success=handle.success,
            duration_seconds=duration,
        )
    except Exception:  # noqa: BLE001 - metrics never block
        pass
    txn = handle.sentry_txn
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
            handle = start_named_transaction(name, op=op)
            try:
                return view_func(*args, **kwargs)
            except Exception:
                handle.success = False
                set_transaction_status(handle, "internal_error")
                raise
            finally:
                finish_transaction(handle)

        return wrapper

    return decorator
