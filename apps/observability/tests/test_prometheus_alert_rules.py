"""SLO-derived Prometheus alert rules (T2).

Pure SimpleTestCase — the generator reads the in-process SLO registry and emits
a rules structure / YAML, no database.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability import slo
from apps.observability.prometheus_alert_rules import (
    build_prometheus_alert_groups,
    metric_base,
    render_prometheus_alert_rules_yaml,
    rules_for_slo,
)

_RATE_KINDS = {"availability", "error_rate", "freshness"}


class MetricBaseTests(SimpleTestCase):
    def test_normalizes_key_to_namespaced_metric(self):
        self.assertEqual(metric_base("web.availability"), "runmycampus_web_availability")
        self.assertEqual(metric_base("ai.gateway.latency"), "runmycampus_ai_gateway_latency")
        self.assertEqual(
            metric_base("ui.friction.validation_retry"),
            "runmycampus_ui_friction_validation_retry",
        )


class RuleGenerationTests(SimpleTestCase):
    def test_every_slo_produces_rules(self):
        for s in slo.SLOS:
            rules = rules_for_slo(s)
            # Every SLO in the registry is either a rate kind or a latency kind
            # with a threshold, so each must yield at least one rule.
            self.assertTrue(rules, f"{s.key} produced no rules")

    def test_rate_slo_emits_fast_and_slow_burn(self):
        s = slo.get_slo("web.availability")
        rules = rules_for_slo(s)
        sevs = sorted(r["labels"]["severity"] for r in rules)
        self.assertEqual(sevs, ["page", "ticket"])
        # Fast-burn threshold = 14.4 * error budget (1 - 0.999) = 0.0144.
        fast = next(r for r in rules if r["labels"]["severity"] == "page")
        self.assertIn("0.0144", fast["expr"])
        self.assertIn("failures_total", fast["expr"])
        self.assertIn("clamp_min", fast["expr"])  # division-by-zero guard

    def test_latency_slo_emits_quantile_threshold(self):
        s = slo.get_slo("attendance.submit")  # 800ms p95
        rules = rules_for_slo(s)
        self.assertEqual(len(rules), 1)
        expr = rules[0]["expr"]
        self.assertIn("histogram_quantile(0.95", expr)
        self.assertIn("duration_seconds_bucket", expr)
        self.assertIn("> 0.8", expr)  # 800ms -> 0.8s

    def test_all_rules_have_required_fields(self):
        groups = build_prometheus_alert_groups()
        rules = groups["groups"][0]["rules"]
        self.assertTrue(rules)
        required = {"alert", "expr", "for", "labels", "annotations"}
        for r in rules:
            self.assertTrue(required <= set(r), f"missing keys in {r.get('alert')}")
            self.assertIn("severity", r["labels"])
            self.assertIn("slo", r["labels"])
            self.assertIn("runbook", r["annotations"])

    def test_alert_names_unique(self):
        rules = build_prometheus_alert_groups()["groups"][0]["rules"]
        names = [r["alert"] for r in rules]
        self.assertEqual(len(names), len(set(names)))

    def test_rule_count_matches_registry(self):
        expected = 0
        for s in slo.SLOS:
            expected += 2 if s.kind in _RATE_KINDS else (1 if s.threshold_ms else 0)
        rules = build_prometheus_alert_groups()["groups"][0]["rules"]
        self.assertEqual(len(rules), expected)


class YamlRenderTests(SimpleTestCase):
    def test_yaml_is_well_formed_and_deterministic(self):
        y1 = render_prometheus_alert_rules_yaml()
        y2 = render_prometheus_alert_rules_yaml()
        self.assertEqual(y1, y2)  # deterministic
        self.assertIn("groups:", y1)
        self.assertIn("rules:", y1)
        self.assertIn("- alert:", y1)
        self.assertTrue(y1.endswith("\n"))
        # Every alert in the structure appears in the rendered YAML.
        for r in build_prometheus_alert_groups()["groups"][0]["rules"]:
            self.assertIn(r["alert"], y1)

    def test_yaml_quotes_promql_expressions(self):
        y = render_prometheus_alert_rules_yaml()
        # PromQL contains { } and > — must be quoted to stay valid YAML.
        for line in y.splitlines():
            if line.strip().startswith("expr:"):
                self.assertIn('expr: "', line)
