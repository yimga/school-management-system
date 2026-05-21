"""SLO clocks service — v3.57.0 (2026-05-21).

Powers the v3.56.0 manager `_slo_clocks.html` partial. Returns one
"clock face" dict per SLO defined in `apps.observability.slo.SLOS` so the
cockpit context can present platform health at a glance.

This module is INTENTIONALLY a thin adapter: it does NOT compute burn-rates
or query Sentry. Real burn-rate computation belongs in the operational
dashboard (`apps/observability/views.py`), where it can read from Sentry,
Prometheus, or the structured-log backend per `OBSERVABILITY_METRICS_BACKEND`.
For the cockpit surface we just want the *shape* — a clock face per SLO with
honest "—" placeholders when no recent telemetry is available.

PII safety:
  * Reads only the SOT registry in `slo.py` — no DB, no request.
  * No tenant slugs, user emails, or other PII land in the returned dicts.

Determinism:
  * With the same SLO registry, the returned list is byte-stable. Tests
    that snapshot the result are safe.

Wave context: shipped as part of the v3.57.0 in-repo platform parity
sweep — pairs with `cockpit_manager_200x._manager_slo_clocks_defaults`
which previously returned hardcoded placeholder clock-faces.
"""

from __future__ import annotations

from typing import Any

from .slo import SLOS, SLODefinition

__all__ = [
    "build_slo_clock_faces",
    "build_clock_face_from_definition",
]


# Severity mapping is policy: under-target SLOs get rendered in `danger`
# orange, near-target in `warn` amber, over-target in `ok` green. The
# thresholds (% of target's distance from 100) are codified here rather
# than in the partial so they're testable in isolation.
_NEAR_TARGET_DISTANCE_PCT = 1.0  # within 1pp of target → warn


def _severity_for(target: float, current: float | None) -> str:
    """Return cockpit severity ("ok" / "warn" / "danger" / "info") for a value.

    `current=None` → "info" (no data yet, render honest "—").
    """
    if current is None:
        return "info"
    if current >= target:
        # over-target ⇒ ok green
        return "ok"
    if (target - current) <= _NEAR_TARGET_DISTANCE_PCT:
        return "warn"
    return "danger"


def _format_percent(value: float | None) -> str:
    """Render an SLO percentage with one decimal — `—` when no data."""
    if value is None:
        return "—"
    # 99.95 → "99.95%"; 100.0 → "100%"
    if value == int(value):
        return f"{int(value)}%"
    return f"{value:.2f}".rstrip("0").rstrip(".") + "%"


def _format_latency_ms(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 1000:
        return f"{value / 1000:.2f}".rstrip("0").rstrip(".") + "s"
    return f"{value}ms"


def build_clock_face_from_definition(
    slo: SLODefinition,
    *,
    current_value: float | None = None,
    burn_rate: float | None = None,
) -> dict[str, Any]:
    """Convert a single `SLODefinition` (+ optional live readings) to a clock-face dict.

    Shape consumed by `_slo_clocks.html`:
        key             str
        label           str
        kind            str   — availability / latency_p95 / latency_p99 / freshness / error_rate
        target_display  str   — "99.9%"  or  "800ms"
        current_display str   — "99.93%" or "—" when no data
        severity        str   — ok / warn / danger / info
        window_days     int
        burn_rate       str   — e.g. "0.3x" / "—"
        burn_severity   str   — ok when < 1x, warn 1-3.99x, danger ≥ 4x
        owner           str
    """
    if slo.kind in ("availability", "error_rate"):
        target_display = _format_percent(slo.target)
        current_display = _format_percent(current_value)
    elif slo.kind == "freshness":
        target_display = _format_percent(slo.target)
        current_display = _format_percent(current_value)
    else:
        # latency_p95 / latency_p99 — threshold_ms is the SLO target
        target_display = _format_latency_ms(slo.threshold_ms)
        # current is interpreted as ms in this branch
        current_display = (
            _format_latency_ms(int(current_value))
            if current_value is not None
            else "—"
        )

    # Severity: for availability/freshness/error_rate, larger is better.
    # For latency, smaller is better — invert the comparison vs target.
    if slo.kind in ("latency_p95", "latency_p99"):
        if current_value is None or slo.threshold_ms is None:
            severity = "info"
        elif current_value <= slo.threshold_ms:
            severity = "ok"
        elif current_value <= slo.threshold_ms * 1.10:
            severity = "warn"
        else:
            severity = "danger"
    else:
        severity = _severity_for(slo.target, current_value)

    # Burn rate severity (Google SRE fast-burn at 14.4×; we surface plain
    # ok/warn/danger to keep the operator's cognitive load low).
    if burn_rate is None:
        burn_display = "—"
        burn_severity = "info"
    elif burn_rate < 1.0:
        burn_display = f"{burn_rate:.2f}x".rstrip("0").rstrip(".") + "x"
        # already has trailing x but we may have stripped trailing zeros — fix:
        burn_display = f"{burn_rate:.2f}x"
        burn_severity = "ok"
    elif burn_rate < 4.0:
        burn_display = f"{burn_rate:.2f}x"
        burn_severity = "warn"
    else:
        burn_display = f"{burn_rate:.1f}x"
        burn_severity = "danger"

    return {
        "key": slo.key,
        "label": slo.label,
        "kind": slo.kind,
        "target_display": target_display,
        "current_display": current_display,
        "severity": severity,
        "window_days": slo.window_days,
        "burn_rate": burn_display,
        "burn_severity": burn_severity,
        "owner": slo.owner,
    }


def build_slo_clock_faces(
    readings: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return one clock-face dict per registered SLO.

    `readings` maps SLO `key` to `{"current": float|None, "burn_rate": float|None}`.
    Missing keys / missing readings render "—" — honest "no data" beats
    fabricated numbers on the operator dashboard.
    """
    readings = readings or {}
    faces: list[dict[str, Any]] = []
    for slo in SLOS:
        r = readings.get(slo.key) or {}
        faces.append(
            build_clock_face_from_definition(
                slo,
                current_value=r.get("current"),
                burn_rate=r.get("burn_rate"),
            )
        )
    return faces
