"""SLO-aligned metric emission — wires slo.py objectives to Prometheus series (T2/T3).

Generated alert rules in ``deploy/observability/slo_alerts.yml`` expect:

* rate SLOs — ``runmycampus_<base>_requests_total`` + ``_failures_total``
* latency SLOs — ``runmycampus_<base>_duration_seconds`` histogram

This module is the canonical emit path. Callers should prefer
:func:`record_traced_transaction` (via ``trace_view`` / ``start_named_transaction``)
or :func:`record_web_availability` (HTTP middleware) rather than ad-hoc counters.
"""
from __future__ import annotations

import logging
from typing import Any

from apps.observability.metrics import emit_counter, emit_histogram
from apps.observability.slo import SLOS, SLOKind, get_slo

logger = logging.getLogger(__name__)

_RATE_KINDS: frozenset[SLOKind] = frozenset({"availability", "error_rate", "freshness"})
_LATENCY_KINDS: frozenset[SLOKind] = frozenset({"latency_p95", "latency_p99"})

_DEFAULT_LATENCY_BUCKETS: tuple[float, ...] = (
    0.05,
    0.1,
    0.25,
    0.5,
    0.8,
    1.0,
    2.5,
    5.0,
    10.0,
    float("inf"),
)

# Sentry / trace transaction name → every SLO key it backs.
#
# One transaction routinely backs more than one objective — auth.login is both
# a latency and an availability SLO. A one-to-one index silently dropped the
# later registration, leaving that SLO with no producer anywhere in the tree
# and its generated burn-rate alert evaluating an absent series forever.
TRANSACTION_TO_SLO: dict[str, list[str]] = {}
for _slo in SLOS:
    for _txn in _slo.sentry_transactions:
        _keys = TRANSACTION_TO_SLO.setdefault(_txn, [])
        if _slo.key not in _keys:
            _keys.append(_slo.key)


def slo_keys_for_transaction(transaction_name: str) -> list[str]:
    """Every SLO key a trace transaction feeds, in registration order."""
    return list(TRANSACTION_TO_SLO.get(transaction_name) or ())


def slo_key_for_transaction(transaction_name: str) -> str | None:
    """Resolve a trace transaction to its primary (first-registered) SLO key."""
    keys = TRANSACTION_TO_SLO.get(transaction_name)
    return keys[0] if keys else None


def _metric_stems(slo_key: str) -> tuple[str, str, str]:
    """Return (requests, failures, duration) metric stems without namespace prefix."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in slo_key).strip("_")
    while "__" in safe:
        safe = safe.replace("__", "_")
    return (
        f"{safe}_requests_total",
        f"{safe}_failures_total",
        f"{safe}_duration_seconds",
    )


def record_slo_outcome(
    slo_key: str,
    *,
    success: bool = True,
    duration_seconds: float | None = None,
    labels: dict[str, Any] | None = None,
) -> None:
    """Record one SLO observation. Never raises."""
    slo = get_slo(slo_key)
    if slo is None:
        return
    try:
        req_name, fail_name, dur_name = _metric_stems(slo_key)
        if slo.kind in _RATE_KINDS:
            emit_counter(req_name, 1, labels=labels)
            if not success:
                emit_counter(fail_name, 1, labels=labels)
        elif slo.kind in _LATENCY_KINDS and duration_seconds is not None:
            emit_histogram(
                dur_name,
                max(0.0, float(duration_seconds)),
                labels=labels,
                buckets=_DEFAULT_LATENCY_BUCKETS,
            )
    except Exception as exc:  # noqa: BLE001 — metrics never break hot path
        logger.warning(
            "slo_metrics record_slo_outcome failed slo=%s err=%s",
            slo_key,
            type(exc).__name__,
        )


def record_web_availability(*, status_code: int, duration_seconds: float | None = None) -> None:
    """Record one HTTP response against the ``web.availability`` SLO."""
    record_slo_outcome(
        "web.availability",
        success=int(status_code) < 500,
        duration_seconds=duration_seconds,
    )


def record_traced_transaction(
    transaction_name: str,
    *,
    success: bool = True,
    duration_seconds: float | None = None,
    labels: dict[str, Any] | None = None,
) -> None:
    """Record metrics for a named trace transaction (``trace_view`` / tasks)."""
    for slo_key in slo_keys_for_transaction(transaction_name):
        # web.availability is recorded by the HTTP middleware for every
        # response; emitting it again here would double-count each request.
        if slo_key == "web.availability":
            continue
        record_slo_outcome(
            slo_key,
            success=success,
            duration_seconds=duration_seconds,
            labels=labels,
        )
