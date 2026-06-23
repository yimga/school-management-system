"""SLO-derived Prometheus alerting rules, as code (T2).

The SLO registry (:mod:`apps.observability.slo`) is the single source of truth
for what the platform promises. This module turns those SLOs into Prometheus
alerting rules so the alert config can't silently drift from the objectives:
change an SLO target and the generated rule changes with it.

Honesty contract — the rules reference a metric NAMING CONVENTION, they do not
invent data:

* rate SLOs (availability / error_rate / freshness) expect
  ``runmycampus_<base>_requests_total`` and ``runmycampus_<base>_failures_total``;
* latency SLOs expect a histogram ``runmycampus_<base>_duration_seconds_bucket``;

where ``<base>`` is the SLO key with ``.``/``-`` normalised to ``_``. Until the
app actually emits those series (``OBSERVABILITY_METRICS_BACKEND=prometheus-client``
plus the emit sites in ``apps/observability/metrics.py``), the rules are INERT —
they evaluate against absent series and never fire. That is the correct,
non-fabricated behaviour: alerts ship with the objective and light up when the
instrumentation lands. ``deploy/observability/README.md`` documents the wiring.

Multi-window burn-rate alerting follows the Google SRE Workbook (the same
thresholds encoded in :func:`apps.observability.slo.burn_rate_severity`):
fast burn (1h, 14.4x budget) pages; slow burn (6h, 6x budget) tickets.

Generate the rules file with::

    python manage.py emit_prometheus_alert_rules > deploy/observability/slo_alerts.yml
"""
from __future__ import annotations

from typing import Any

from apps.observability.slo import SLOS, SLODefinition

# Metric namespace — matches OBSERVABILITY_PROMETHEUS_NAMESPACE default.
_NS = "runmycampus"
# Latency quantile assessed (p95 / p99 map to the same histogram quantile expr).
_QUANTILE = {"latency_p95": "0.95", "latency_p99": "0.99"}
_RATE_KINDS = {"availability", "error_rate", "freshness"}


def metric_base(slo_key: str) -> str:
    """Prometheus-safe metric base for an SLO key (``a.b-c`` -> ``runmycampus_a_b_c``)."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in slo_key).strip("_")
    while "__" in safe:
        safe = safe.replace("__", "_")
    return f"{_NS}_{safe}"


def _alert_name(slo_key: str, suffix: str) -> str:
    parts = [p.capitalize() for p in slo_key.replace("-", "_").split(".")]
    return "SLO" + "".join("".join(w.capitalize() for w in p.split("_")) for p in parts) + suffix


def _error_budget(target: float) -> float:
    # Fraction of requests allowed to fail (e.g. target 99.9 -> 0.001).
    return round(max(0.0, 1.0 - (target / 100.0)), 6)


def _burn_expr(base: str, window: str, factor: float, budget: float) -> str:
    threshold = round(factor * budget, 8)
    return (
        f"(sum(rate({base}_failures_total[{window}])) "
        f"/ clamp_min(sum(rate({base}_requests_total[{window}])), 1)) "
        f"> {threshold}"
    )


def _rate_slo_rules(slo: SLODefinition) -> list[dict[str, Any]]:
    base = metric_base(slo.key)
    budget = _error_budget(slo.target)
    if budget <= 0:
        return []
    common = {"slo": slo.key, "owner": slo.owner, "kind": slo.kind}
    # Fast burn: 1h window, 14.4x budget -> page. Slow burn: 6h, 6x -> ticket.
    return [
        {
            "alert": _alert_name(slo.key, "FastBurn"),
            "expr": _burn_expr(base, "1h", 14.4, budget),
            "for": "2m",
            "labels": {**common, "severity": "page"},
            "annotations": {
                "summary": f"{slo.label}: fast error-budget burn",
                "description": (
                    f"{slo.label} is burning its {slo.window_days}d error budget "
                    f"at >=14.4x (target {slo.target}%). At this rate ~2% of the "
                    f"budget is gone in 1h."
                ),
                "runbook": "docs/OBSERVABILITY_METRICS.md",
            },
        },
        {
            "alert": _alert_name(slo.key, "SlowBurn"),
            "expr": _burn_expr(base, "6h", 6.0, budget),
            "for": "15m",
            "labels": {**common, "severity": "ticket"},
            "annotations": {
                "summary": f"{slo.label}: sustained error-budget burn",
                "description": (
                    f"{slo.label} is burning its {slo.window_days}d error budget "
                    f"at >=6x (target {slo.target}%) over 6h."
                ),
                "runbook": "docs/OBSERVABILITY_METRICS.md",
            },
        },
    ]


def _latency_slo_rule(slo: SLODefinition) -> list[dict[str, Any]]:
    if not slo.threshold_ms:
        return []
    base = metric_base(slo.key)
    quantile = _QUANTILE.get(slo.kind, "0.95")
    threshold_seconds = round(slo.threshold_ms / 1000.0, 4)
    qlabel = "p99" if slo.kind == "latency_p99" else "p95"
    return [
        {
            "alert": _alert_name(slo.key, f"Latency{qlabel.upper()}"),
            "expr": (
                f"histogram_quantile({quantile}, "
                f"sum by (le) (rate({base}_duration_seconds_bucket[5m]))) "
                f"> {threshold_seconds}"
            ),
            "for": "10m",
            "labels": {"slo": slo.key, "owner": slo.owner, "kind": slo.kind, "severity": "ticket"},
            "annotations": {
                "summary": f"{slo.label}: {qlabel} above {slo.threshold_ms}ms",
                "description": (
                    f"{qlabel} latency for {slo.key} has exceeded its "
                    f"{slo.threshold_ms}ms objective for 10m."
                ),
                "runbook": "docs/OBSERVABILITY_METRICS.md",
            },
        }
    ]


def rules_for_slo(slo: SLODefinition) -> list[dict[str, Any]]:
    if slo.kind in _RATE_KINDS:
        return _rate_slo_rules(slo)
    if slo.kind in _QUANTILE:
        return _latency_slo_rule(slo)
    return []


def build_prometheus_alert_groups() -> dict[str, Any]:
    """Build the Prometheus ``{"groups": [...]}`` structure from the SLO registry."""
    rules: list[dict[str, Any]] = []
    for slo in SLOS:
        rules.extend(rules_for_slo(slo))
    return {"groups": [{"name": "runmycampus_slo_alerts", "rules": rules}]}


def _yaml_quote(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_prometheus_alert_rules_yaml() -> str:
    """Render the alert groups to a deterministic Prometheus rules YAML string.

    A small purpose-built emitter (no external YAML dependency) so the output is
    stable for diffing in CI. Every scalar is double-quoted, which is valid YAML
    and safe for PromQL expressions that contain ``{``, ``}`` and ``>``.
    """
    groups = build_prometheus_alert_groups()
    lines: list[str] = [
        "# GENERATED from apps/observability/slo.py via",
        "# `python manage.py emit_prometheus_alert_rules`. Do not edit by hand.",
        "# Rules are INERT until the app emits the referenced metrics — see",
        "# deploy/observability/README.md.",
        "groups:",
    ]
    for group in groups["groups"]:
        lines.append(f"  - name: {_yaml_quote(group['name'])}")
        lines.append("    rules:")
        for rule in group["rules"]:
            lines.append(f"      - alert: {_yaml_quote(rule['alert'])}")
            lines.append(f"        expr: {_yaml_quote(rule['expr'])}")
            lines.append(f"        for: {_yaml_quote(rule['for'])}")
            lines.append("        labels:")
            for k, v in rule["labels"].items():
                lines.append(f"          {k}: {_yaml_quote(v)}")
            lines.append("        annotations:")
            for k, v in rule["annotations"].items():
                lines.append(f"          {k}: {_yaml_quote(v)}")
    return "\n".join(lines) + "\n"


__all__ = [
    "metric_base",
    "rules_for_slo",
    "build_prometheus_alert_groups",
    "render_prometheus_alert_rules_yaml",
]
