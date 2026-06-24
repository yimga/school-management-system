#!/usr/bin/env python3
"""Verify T2/T3 Prometheus observability collector stack is wired and drift-free (batch 1718)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIRED_FILES = (
    "deploy/observability/docker-compose.yml",
    "deploy/observability/prometheus.yml",
    "deploy/observability/slo_alerts.yml",
    "deploy/observability/README.md",
    "deploy/observability/grafana/provisioning/datasources/prometheus.yml",
    "docs/OBSERVABILITY_METRICS.md",
    "docs/PROMETHEUS_OPERATOR_DEPLOY_RUNBOOK.md",
    "apps/observability/slo_metrics.py",
    "scripts/verify_slo_metrics_emit_sites.py",
    "scripts/verify_prometheus_stack_live.py",
)


def _fail(msg: str) -> None:
    print(f"PROMETHEUS_OBSERVABILITY_STACK_FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            _fail(f"missing {rel}")

    prom_yml = (ROOT / "deploy/observability/prometheus.yml").read_text(encoding="utf-8")
    for needle in ("rule_files:", "slo_alerts.yml", "runmycampus-web", "/metrics/"):
        if needle not in prom_yml:
            _fail(f"prometheus.yml missing {needle!r}")

    compose = (ROOT / "deploy/observability/docker-compose.yml").read_text(encoding="utf-8")
    for needle in ("prom/prometheus", "grafana/grafana-oss", "slo_alerts.yml"):
        if needle not in compose:
            _fail(f"docker-compose.yml missing {needle!r}")

    readme = (ROOT / "deploy/observability/README.md").read_text(encoding="utf-8")
    if "prometheus-client" not in readme:
        _fail("README.md must document prometheus-client backend gate")

    metrics_doc = (ROOT / "docs/OBSERVABILITY_METRICS.md").read_text(encoding="utf-8")
    if "OBSERVABILITY_METRICS_BACKEND" not in metrics_doc:
        _fail("OBSERVABILITY_METRICS.md missing backend selector docs")

    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.observability.prometheus_alert_rules import render_prometheus_alert_rules_yaml

    generated = render_prometheus_alert_rules_yaml()
    committed = (ROOT / "deploy/observability/slo_alerts.yml").read_text(encoding="utf-8")
    if generated != committed:
        _fail(
            "slo_alerts.yml drift — run: "
            "python manage.py emit_prometheus_alert_rules > deploy/observability/slo_alerts.yml"
        )

    print("PROMETHEUS_OBSERVABILITY_STACK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
