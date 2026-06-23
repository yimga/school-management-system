"""Emit SLO-derived Prometheus alerting rules to stdout (T2).

    python manage.py emit_prometheus_alert_rules > deploy/observability/slo_alerts.yml

The output is generated from the SLO registry (apps/observability/slo.py), so the
alert config never drifts from the objectives. See
apps/observability/prometheus_alert_rules.py for the metric-naming contract.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.observability.prometheus_alert_rules import render_prometheus_alert_rules_yaml


class Command(BaseCommand):
    help = "Print SLO-derived Prometheus alerting rules (YAML) to stdout."

    def handle(self, *args, **options):
        # Write directly so YAML is not wrapped/indented by the style helpers.
        self.stdout.write(render_prometheus_alert_rules_yaml(), ending="")
