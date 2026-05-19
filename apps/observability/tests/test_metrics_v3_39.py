"""Tests for the v3.39.0 Agent 4 observability metrics bridge.

Covers:

* The 4 backends (noop / structured-log / prometheus-client / statsd).
* `_sanitize_labels` rule by rule (sensitive drop / truncate / key normalize).
* Auto-fallback when prometheus_client / statsd lib is missing.
* `/metrics/` view content-type + payload.
* assertLogs confirms no PII / secret material in metric emission lines
  even when the caller supplies sensitive-shaped labels.
* Backwards-compat: `tags=` kwarg from v3.38 Agent 4 still works.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.observability import metrics as obs_metrics


class SanitizeLabelsTests(SimpleTestCase):
    """`_sanitize_labels` — 8+ cases covering every rule."""

    def test_none_returns_empty_dict(self) -> None:
        self.assertEqual(obs_metrics._sanitize_labels(None), {})

    def test_empty_dict_returns_empty_dict(self) -> None:
        self.assertEqual(obs_metrics._sanitize_labels({}), {})

    def test_drops_label_with_password_in_value(self) -> None:
        out = obs_metrics._sanitize_labels({"auth": "user_password=swordfish"})
        self.assertNotIn("auth", out)

    def test_drops_label_with_token_in_value(self) -> None:
        out = obs_metrics._sanitize_labels({"hdr": "Bearer my-secret-token-value"})
        self.assertNotIn("hdr", out)

    def test_drops_label_with_email_in_value(self) -> None:
        out = obs_metrics._sanitize_labels({"src": "user@example.com_email_field"})
        self.assertNotIn("src", out)

    def test_drops_label_with_slug_in_value(self) -> None:
        # Per Agent 4 prompt — slugs are tenant-identifying.
        out = obs_metrics._sanitize_labels({"x": "acme-prep-slug-here"})
        self.assertNotIn("x", out)

    def test_truncates_long_values_to_64(self) -> None:
        long_val = "x" * 200
        out = obs_metrics._sanitize_labels({"k": long_val})
        self.assertEqual(len(out["k"]), 64)

    def test_normalizes_uppercase_key_to_lowercase(self) -> None:
        out = obs_metrics._sanitize_labels({"TenantID": "abc"})
        self.assertIn("tenantid", out)
        self.assertEqual(out["tenantid"], "abc")

    def test_normalizes_invalid_key_chars_to_underscore(self) -> None:
        out = obs_metrics._sanitize_labels({"my-key.path": "abc"})
        self.assertIn("my_key_path", out)

    def test_prepends_underscore_when_key_starts_with_digit(self) -> None:
        out = obs_metrics._sanitize_labels({"123abc": "x"})
        self.assertIn("_123abc", out)

    def test_handles_int_value(self) -> None:
        out = obs_metrics._sanitize_labels({"count": 42})
        self.assertEqual(out["count"], "42")

    def test_handles_none_value_as_empty_string(self) -> None:
        out = obs_metrics._sanitize_labels({"x": None})
        self.assertEqual(out["x"], "")


class NoopBackendTests(SimpleTestCase):
    """Default `noop` backend: callable, returns None, no side effects."""

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="noop")
    def test_emit_counter_noop_returns_none(self) -> None:
        result = obs_metrics.emit_counter("test.x", labels={"a": "b"})
        self.assertIsNone(result)

    @override_settings(OBSERVABILITY_METRICS_BACKEND="noop")
    def test_emit_gauge_noop_returns_none(self) -> None:
        result = obs_metrics.emit_gauge("test.x", 1.0, labels={"a": "b"})
        self.assertIsNone(result)


class StructuredLogBackendTests(SimpleTestCase):
    """`structured-log` backend: one JSON line per call, secret-safe."""

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="structured-log")
    def test_emit_counter_logs_json_line(self) -> None:
        with self.assertLogs("observability.metrics", level="INFO") as cm:
            obs_metrics.emit_counter("test.counter", 3, labels={"region": "us-east"})
        # Expect exactly one INFO record carrying our JSON payload.
        joined = "\n".join(cm.output)
        self.assertIn("test.counter", joined)
        self.assertIn("counter", joined)
        self.assertIn("us-east", joined)

    @override_settings(OBSERVABILITY_METRICS_BACKEND="structured-log")
    def test_emit_counter_strips_sensitive_label_value(self) -> None:
        with self.assertLogs("observability.metrics", level="INFO") as cm:
            obs_metrics.emit_counter(
                "test.counter",
                labels={"auth_header": "Bearer my-secret-token", "ok": "fine"},
            )
        joined = "\n".join(cm.output)
        # The sensitive value must not appear in the emission line.
        self.assertNotIn("Bearer", joined)
        self.assertNotIn("my-secret-token", joined)
        # The benign label is kept.
        self.assertIn("fine", joined)

    @override_settings(OBSERVABILITY_METRICS_BACKEND="structured-log")
    def test_emit_gauge_logs_kind_gauge(self) -> None:
        with self.assertLogs("observability.metrics", level="INFO") as cm:
            obs_metrics.emit_gauge("test.gauge", 12.5, labels={"k": "v"})
        joined = "\n".join(cm.output)
        self.assertIn("gauge", joined)
        self.assertIn("12.5", joined)

    @override_settings(OBSERVABILITY_METRICS_BACKEND="structured-log")
    def test_emit_histogram_logs_kind_histogram(self) -> None:
        with self.assertLogs("observability.metrics", level="INFO") as cm:
            obs_metrics.emit_histogram("test.h", 0.05)
        joined = "\n".join(cm.output)
        self.assertIn("histogram", joined)

    @override_settings(OBSERVABILITY_METRICS_BACKEND="structured-log")
    def test_tags_kwarg_backwards_compat(self) -> None:
        """v3.38 Agent 4 passes `tags=` — must still work."""
        with self.assertLogs("observability.metrics", level="INFO") as cm:
            obs_metrics.emit_counter("test.compat", tags={"x": "y"})
        joined = "\n".join(cm.output)
        self.assertIn("test.compat", joined)


class AutoFallbackTests(SimpleTestCase):
    """Backend requested but library missing → fallback to structured-log."""

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="prometheus-client")
    def test_prometheus_missing_lib_falls_back_to_log_and_warns(self) -> None:
        # Pretend prometheus_client isn't installed.
        with patch(
            "apps.observability.metrics.importlib.util.find_spec",
            return_value=None,
        ):
            with self.assertLogs("observability.metrics", level="WARNING") as cm:
                name, backend = obs_metrics._get_backend()
        self.assertEqual(name, "structured-log")
        # The warning fires exactly once on first backend resolution.
        warning_lines = [m for m in cm.output if "WARNING" in m]
        self.assertEqual(len(warning_lines), 1)
        self.assertIn("prometheus-client", warning_lines[0])

    @override_settings(OBSERVABILITY_METRICS_BACKEND="statsd")
    def test_statsd_missing_lib_falls_back_to_log_and_warns(self) -> None:
        with patch(
            "apps.observability.metrics.importlib.util.find_spec",
            return_value=None,
        ):
            with self.assertLogs("observability.metrics", level="WARNING") as cm:
                name, backend = obs_metrics._get_backend()
        self.assertEqual(name, "structured-log")
        self.assertIn("statsd", "\n".join(cm.output))


class _FakeCounter:
    def __init__(self) -> None:
        self.inc_calls: list[tuple[float, dict]] = []
        self._labels: dict | None = None

    def labels(self, **labels):
        self._labels = labels
        return self

    def inc(self, value: float = 1.0) -> None:
        self.inc_calls.append((value, self._labels or {}))


class _FakeGauge:
    def __init__(self) -> None:
        self.set_calls: list[tuple[float, dict]] = []
        self._labels: dict | None = None

    def labels(self, **labels):
        self._labels = labels
        return self

    def set(self, value: float) -> None:
        self.set_calls.append((value, self._labels or {}))


class _FakeHistogram:
    def __init__(self) -> None:
        self.observe_calls: list[tuple[float, dict]] = []
        self._labels: dict | None = None

    def labels(self, **labels):
        self._labels = labels
        return self

    def observe(self, value: float) -> None:
        self.observe_calls.append((value, self._labels or {}))


class PrometheusBackendTests(SimpleTestCase):
    """Verify the prometheus-client backend wires through to the lib."""

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()
        self._fake_counter = _FakeCounter()
        self._fake_gauge = _FakeGauge()
        self._fake_histogram = _FakeHistogram()
        fake_module = types.ModuleType("prometheus_client")
        fake_module.Counter = MagicMock(return_value=self._fake_counter)
        fake_module.Gauge = MagicMock(return_value=self._fake_gauge)
        fake_module.Histogram = MagicMock(return_value=self._fake_histogram)
        fake_module.CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
        fake_module.generate_latest = MagicMock(return_value=b"# HELP x\n")
        self._fake_module = fake_module
        # Inject the fake under both find_spec and import.
        self._find_spec_patch = patch(
            "apps.observability.metrics.importlib.util.find_spec",
            return_value=MagicMock(name="spec"),
        )
        self._import_patch = patch(
            "apps.observability.metrics.importlib.import_module",
            return_value=fake_module,
        )
        self._find_spec_patch.start()
        self._import_patch.start()

    def tearDown(self) -> None:
        self._find_spec_patch.stop()
        self._import_patch.stop()
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="prometheus-client")
    def test_emit_counter_routes_to_prometheus_counter_inc(self) -> None:
        obs_metrics.emit_counter("test.c", 2, labels={"region": "us"})
        self.assertEqual(len(self._fake_counter.inc_calls), 1)
        value, labels = self._fake_counter.inc_calls[0]
        self.assertEqual(value, 2.0)
        self.assertEqual(labels, {"region": "us"})

    @override_settings(OBSERVABILITY_METRICS_BACKEND="prometheus-client")
    def test_emit_gauge_routes_to_prometheus_gauge_set(self) -> None:
        obs_metrics.emit_gauge("test.g", 99.5, labels={"region": "us"})
        self.assertEqual(len(self._fake_gauge.set_calls), 1)
        value, labels = self._fake_gauge.set_calls[0]
        self.assertEqual(value, 99.5)
        self.assertEqual(labels, {"region": "us"})

    @override_settings(OBSERVABILITY_METRICS_BACKEND="prometheus-client")
    def test_emit_histogram_routes_to_prometheus_histogram_observe(self) -> None:
        obs_metrics.emit_histogram("test.h", 0.123, labels={"endpoint": "x"})
        self.assertEqual(len(self._fake_histogram.observe_calls), 1)
        value, labels = self._fake_histogram.observe_calls[0]
        self.assertEqual(value, 0.123)

    @override_settings(
        OBSERVABILITY_METRICS_BACKEND="prometheus-client",
        OBSERVABILITY_PROMETHEUS_NAMESPACE="runmycampus",
    )
    def test_metric_name_gets_namespace_prefix(self) -> None:
        obs_metrics.emit_counter("foo.bar")
        # The Counter constructor was called with the namespaced name.
        called_name = self._fake_module.Counter.call_args[0][0]
        self.assertTrue(called_name.startswith("runmycampus_"))
        self.assertIn("foo_bar", called_name)


class _FakeStatsdClient:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.incr_calls: list[tuple[str, int]] = []
        self.gauge_calls: list[tuple[str, float]] = []
        self.timing_calls: list[tuple[str, float]] = []

    def incr(self, name: str, value: int = 1) -> None:
        self.incr_calls.append((name, value))

    def gauge(self, name: str, value: float) -> None:
        self.gauge_calls.append((name, value))

    def timing(self, name: str, value: float) -> None:
        self.timing_calls.append((name, value))


class StatsdBackendTests(SimpleTestCase):
    """statsd backend wires to incr / gauge / timing with tag suffix."""

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()
        self._fake_clients: list[_FakeStatsdClient] = []

        def _make_client(host, port):
            client = _FakeStatsdClient(host, port)
            self._fake_clients.append(client)
            return client

        fake_module = types.ModuleType("statsd")
        fake_module.StatsClient = _make_client
        self._find_spec_patch = patch(
            "apps.observability.metrics.importlib.util.find_spec",
            return_value=MagicMock(name="spec"),
        )
        self._import_patch = patch(
            "apps.observability.metrics.importlib.import_module",
            return_value=fake_module,
        )
        self._find_spec_patch.start()
        self._import_patch.start()

    def tearDown(self) -> None:
        self._find_spec_patch.stop()
        self._import_patch.stop()
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="statsd")
    def test_emit_counter_calls_statsd_incr_with_tags(self) -> None:
        obs_metrics.emit_counter("test.c", 5, labels={"region": "us"})
        client = self._fake_clients[0]
        self.assertEqual(len(client.incr_calls), 1)
        name, value = client.incr_calls[0]
        self.assertIn("test.c", name)
        self.assertIn("region:us", name)
        self.assertEqual(value, 5)


class PrometheusViewTests(SimpleTestCase):
    """`PrometheusMetricsView` returns 200 + correct content-type when the
    prom_client module is importable.
    """

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()

    def test_view_returns_404_when_prom_client_missing(self) -> None:
        from apps.observability.views_metrics import PrometheusMetricsView
        from django.test import RequestFactory

        rf = RequestFactory()
        view = PrometheusMetricsView.as_view()
        # Simulate prometheus_client missing by intercepting import_module.
        real_import = importlib.import_module

        def _fail_for_pc(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("simulated missing")
            return real_import(name, *args, **kwargs)

        with patch(
            "apps.observability.views_metrics.importlib.import_module",
            side_effect=_fail_for_pc,
        ):
            resp = view(rf.get("/metrics/"))
        self.assertEqual(resp.status_code, 404)

    def test_view_returns_200_with_text_plain_content_type(self) -> None:
        from apps.observability.views_metrics import PrometheusMetricsView
        from django.test import RequestFactory

        fake_pc = types.ModuleType("prometheus_client")
        fake_pc.generate_latest = MagicMock(return_value=b"# HELP test\n")
        fake_pc.CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
        with patch(
            "apps.observability.views_metrics.importlib.import_module",
            return_value=fake_pc,
        ):
            rf = RequestFactory()
            view = PrometheusMetricsView.as_view()
            resp = view(rf.get("/metrics/"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp["Content-Type"])
        self.assertIn(b"# HELP test", resp.content)


class IdempotentBackendSelectionTests(SimpleTestCase):
    """Repeated emit_* calls don't re-initialize the backend."""

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="structured-log")
    def test_repeated_emit_uses_cached_backend(self) -> None:
        # First call resolves + caches.
        obs_metrics.emit_counter("test.idem", 1)
        first_name, first_backend = obs_metrics._get_backend()
        # Second call must return the SAME backend instance.
        obs_metrics.emit_counter("test.idem", 1)
        second_name, second_backend = obs_metrics._get_backend()
        self.assertIs(first_backend, second_backend)
        self.assertEqual(first_name, second_name)


class V338BackwardsCompatTests(SimpleTestCase):
    """v3.38 Agent 4's `apps/migration_cloud/metrics.py` introspects
    `services.observability` and `apps.observability.metrics` for
    `emit_counter` / `emit_gauge`. Both paths must resolve.
    """

    def test_services_observability_exports_emit_counter(self) -> None:
        from services import observability as svc_obs

        self.assertTrue(callable(getattr(svc_obs, "emit_counter", None)))
        self.assertTrue(callable(getattr(svc_obs, "emit_gauge", None)))

    def test_apps_observability_metrics_exports_emit_counter(self) -> None:
        from apps.observability import metrics as obs_metrics_mod

        self.assertTrue(callable(getattr(obs_metrics_mod, "emit_counter", None)))
        self.assertTrue(callable(getattr(obs_metrics_mod, "emit_gauge", None)))

    def test_apps_observability_package_reexports_emit_counter(self) -> None:
        from apps import observability as obs_pkg

        self.assertTrue(callable(getattr(obs_pkg, "emit_counter", None)))
        self.assertTrue(callable(getattr(obs_pkg, "emit_gauge", None)))
        self.assertTrue(callable(getattr(obs_pkg, "emit_histogram", None)))


class NoSecretLeakageInEmissionTests(SimpleTestCase):
    """assertLogs guard — even when a caller hands us labels with
    sensitive values, the emission line never contains them.
    """

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="structured-log")
    def test_password_value_never_appears_in_logged_payload(self) -> None:
        with self.assertLogs("observability.metrics", level="INFO") as cm:
            obs_metrics.emit_counter(
                "test.leak",
                labels={
                    "leaky": "user-password=hunter2",
                    "also_leaky": "Bearer my-token-here",
                    "ssn_field": "123-45-6789-ssn",
                    "fine": "ok",
                },
            )
        joined = "\n".join(cm.output)
        self.assertNotIn("hunter2", joined)
        self.assertNotIn("my-token-here", joined)
        self.assertNotIn("123-45-6789", joined)
        # The benign label survives.
        self.assertIn("fine", joined)


class UnknownBackendFallbackTests(SimpleTestCase):
    """Misconfigured backend name falls back to structured-log."""

    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()

    @override_settings(OBSERVABILITY_METRICS_BACKEND="not-a-real-backend")
    def test_unknown_backend_falls_back(self) -> None:
        with self.assertLogs("observability.metrics", level="WARNING") as cm:
            name, backend = obs_metrics._get_backend()
        self.assertEqual(name, "structured-log")
        self.assertIn("not-a-real-backend", "\n".join(cm.output))
