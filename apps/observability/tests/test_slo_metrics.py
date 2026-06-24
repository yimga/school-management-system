"""SLO metrics emit wiring tests (batch 1705 — T2/T3 live instrumentation)."""
from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.observability import metrics as obs_metrics
from apps.observability.slo_metrics import (
    TRANSACTION_TO_SLO,
    record_slo_outcome,
    record_web_availability,
    slo_key_for_transaction,
)
from apps.observability.tracing import finish_transaction, start_named_transaction, trace_view


class SloMetricsMappingTests(SimpleTestCase):
    def test_transaction_index_covers_hot_paths(self):
        for txn in (
            "auth.login",
            "attendance.submit",
            "grade.entry",
            "webhook.deliver",
            "ai.gateway.invoke",
            "migration.bundle_apply",
            "sync.delta_apply",
        ):
            self.assertIn(txn, TRANSACTION_TO_SLO)

    def test_slo_key_for_auth_login(self):
        self.assertEqual(slo_key_for_transaction("auth.login"), "auth.login")


class SloMetricsEmitTests(SimpleTestCase):
    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()
        self.emitted: list[tuple[str, str, float]] = []

        def _counter(name: str, value: float = 1, *, labels=None, tags=None):
            self.emitted.append(("counter", name, float(value)))

        def _histogram(name: str, value: float, *, labels=None, tags=None, buckets=None):
            self.emitted.append(("histogram", name, float(value)))

        self._counter_patch = patch(
            "apps.observability.slo_metrics.emit_counter", side_effect=_counter
        )
        self._hist_patch = patch(
            "apps.observability.slo_metrics.emit_histogram", side_effect=_histogram
        )
        self._counter_patch.start()
        self._hist_patch.start()

    def tearDown(self) -> None:
        self._counter_patch.stop()
        self._hist_patch.stop()
        obs_metrics._reset_backend_cache()

    def test_web_availability_emits_request_counter(self):
        record_web_availability(status_code=200)
        self.assertTrue(any(e[1].endswith("_requests_total") for e in self.emitted))

    def test_web_availability_5xx_emits_failure(self):
        record_web_availability(status_code=503)
        stems = [e[1] for e in self.emitted if e[0] == "counter"]
        self.assertIn("web_availability_requests_total", stems)
        self.assertIn("web_availability_failures_total", stems)

    def test_latency_slo_emits_histogram(self):
        record_slo_outcome("auth.login", success=True, duration_seconds=0.42)
        self.assertEqual(len(self.emitted), 1)
        kind, name, value = self.emitted[0]
        self.assertEqual(kind, "histogram")
        self.assertEqual(name, "auth_login_duration_seconds")
        self.assertAlmostEqual(value, 0.42)


class TraceHandleSloTests(SimpleTestCase):
    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()
        self.emitted: list[str] = []

        def _record(name, *, success=True, duration_seconds=None, labels=None):
            self.emitted.append(name)

        self._patch = patch(
            "apps.observability.slo_metrics.record_traced_transaction",
            side_effect=_record,
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        obs_metrics._reset_backend_cache()

    def test_finish_transaction_records_trace_name(self):
        handle = start_named_transaction("webhook.deliver")
        finish_transaction(handle)
        self.assertEqual(self.emitted, ["webhook.deliver"])

    def test_trace_view_records_on_success(self):
        @trace_view("grade.entry")
        def _ok():
            return "ok"

        self.assertEqual(_ok(), "ok")
        self.assertEqual(self.emitted, ["grade.entry"])
