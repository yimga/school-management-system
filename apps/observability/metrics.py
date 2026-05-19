"""Observability metrics bridge (v3.39.0 Agent 4).

Pluggable backend dispatch for platform metric emission. The
v3.38.0 Agent 4 ``apps/migration_cloud/metrics.py`` helpers
introspect this module for ``emit_counter`` / ``emit_gauge``
callables and route Migration Cloud's 6 typed ``record_*()``
helpers through whichever backend is active. Pre-v3.39.0, the
introspection always fell back to structured-JSON logging; this
module formalizes that path AND adds real ``prometheus_client``
and ``statsd`` backends so metrics flow to operator dashboards
without the log-forwarder shim.

Backends (selected via ``settings.OBSERVABILITY_METRICS_BACKEND``):

* ``noop`` (default) — every helper silently returns. Production
  with no metric sink configured looks like this; calling code
  pays only the function-call cost.
* ``structured-log`` — emits one structured-JSON line per call on
  ``logging.getLogger("observability.metrics")`` at INFO. Operators
  ship via Vector / Fluent Bit. Same behavior as v3.38 Agent 4's
  inline fallback, formalized here.
* ``prometheus-client`` — wraps the ``prometheus_client`` library
  if installed. Counter / Gauge / Histogram instances are cached
  per metric name so repeated emissions don't re-register. The
  HTTP exporter view at ``/metrics/`` is wired (lazy include) when
  this backend is active.
* ``statsd`` — wraps the ``statsd`` library if installed. Tags are
  serialized DataDog-style (``#tag:value,tag:value``).

If a backend is requested but its library is not installed, the
module falls back to ``structured-log`` AND logs a single WARNING
on initialization. This avoids the production-hot-path failure
mode where metric emission silently disappears AND avoids hard
import of optional dependencies.

Label discipline (``_sanitize_labels``):

* Drops labels whose VALUE contains a sensitive keyword (mirrors
  the ``scan_pii_logging_smell.py`` keyword list). Prevents
  passwords / tokens / secrets / private keys / etc. from
  accidentally landing in metric labels (where they would
  cardinality-explode AND leak).
* Truncates long values to 64 chars (Prometheus best-practice).
* Normalizes keys to ``[a-z_][a-z0-9_]*`` (Prometheus rule —
  invalid keys would fail registration with prometheus_client).

Backwards compat with v3.38.0 Agent 4:

* ``emit_counter(name, value=1, *, labels=None)`` and
  ``emit_gauge(name, value, *, labels=None)`` are exported.
* v3.38 Agent 4's introspection passes ``tags=`` kwarg (legacy
  name); both ``tags=`` and ``labels=`` are accepted.

Library imports are LAZY — ``prometheus_client`` / ``statsd``
MUST NOT be required runtime dependencies; probe via
``importlib.util.find_spec`` and import only when the backend
is active.
"""
from __future__ import annotations

import atexit
import importlib
import importlib.util
import json
import logging
import re
import threading
from typing import Any

logger = logging.getLogger("observability.metrics")

# ─── Sensitive label scrubbing ──────────────────────────────────────────

# Mirrors `scripts/scan_pii_logging_smell.py::SENSITIVE_KEYWORDS` so the
# scanner-enforced "do not log PII" contract extends to metric labels.
# Added `email` and `slug` per Agent 4 prompt — both can be PII or
# tenant-identifying and have no place in a Prometheus label.
_SENSITIVE_KEYWORDS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "signature_text",
    "private_key",
    "email",
    "slug",
    "ssn",
    "dob",
    "api_key",
    "apikey",
)

# Prometheus label-name rule: `[a-z_][a-z0-9_]*` — non-conforming
# characters become underscores.
_LABEL_KEY_INVALID = re.compile(r"[^a-z0-9_]")
_LABEL_VALUE_MAX_LEN = 64


def _sanitize_labels(labels: dict[str, Any] | None) -> dict[str, str]:
    """Return a Prometheus-safe copy of ``labels``.

    Three transforms, in order:

    1. Drop any key whose VALUE (lowercased) contains a sensitive
       keyword. We check the value rather than the key because callers
       legitimately tag with key names like ``"token_type"`` (the
       category is non-PII) but the VALUE side would smuggle the secret.
    2. Truncate values to 64 chars.
    3. Lowercase keys; replace invalid chars with ``_``; ensure leading
       char is alpha or ``_`` (prepend ``_`` if it starts with a digit).

    Returns ``{}`` for ``None`` / empty input.
    """
    if not labels:
        return {}
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in labels.items():
        if raw_key is None:
            continue
        # Stringify FIRST so int/bool labels work.
        try:
            value_str = str(raw_value) if raw_value is not None else ""
        except Exception:  # noqa: BLE001 - never raise from a metric label
            value_str = ""

        # Sensitive-value check (case-insensitive substring).
        lowered = value_str.lower()
        if any(kw in lowered for kw in _SENSITIVE_KEYWORDS):
            # Drop the entire label; sensitive data must not reach
            # the metric sink even if the caller asked to label by it.
            continue

        # Truncate long values.
        if len(value_str) > _LABEL_VALUE_MAX_LEN:
            value_str = value_str[:_LABEL_VALUE_MAX_LEN]

        # Normalize key.
        key_str = str(raw_key).lower()
        key_str = _LABEL_KEY_INVALID.sub("_", key_str)
        if not key_str:
            continue
        if not (key_str[0].isalpha() or key_str[0] == "_"):
            key_str = "_" + key_str
        cleaned[key_str] = value_str
    return cleaned


# ─── Backend selection ──────────────────────────────────────────────────

# Cached so repeated emit_* calls don't re-init the backend. Holds the
# resolved backend object (or None for noop).
_backend_lock = threading.Lock()
_backend_cache: dict[str, Any] = {"resolved": False, "backend": None, "name": "noop"}


def _resolve_settings_backend() -> str:
    """Return the configured backend name, defaulting to ``"noop"``."""
    try:
        from django.conf import settings

        return getattr(settings, "OBSERVABILITY_METRICS_BACKEND", "noop") or "noop"
    except Exception:  # noqa: BLE001 - Django not yet configured during scripts
        return "noop"


def _get_backend() -> tuple[str, Any]:
    """Return ``(backend_name, backend_object)``. Idempotent — caches
    after first resolution.
    """
    if _backend_cache["resolved"]:
        return _backend_cache["name"], _backend_cache["backend"]
    with _backend_lock:
        if _backend_cache["resolved"]:
            return _backend_cache["name"], _backend_cache["backend"]
        configured = _resolve_settings_backend()
        name, backend = _build_backend(configured)
        _backend_cache["resolved"] = True
        _backend_cache["name"] = name
        _backend_cache["backend"] = backend
    return name, backend


def _reset_backend_cache() -> None:
    """Test-helper — clears the cached backend so each test can pick a
    fresh one via ``override_settings``. Not part of the public API.
    """
    with _backend_lock:
        _backend_cache["resolved"] = False
        _backend_cache["name"] = "noop"
        _backend_cache["backend"] = None


def _build_backend(name: str) -> tuple[str, Any]:
    """Construct the backend object for ``name``. Returns
    ``(effective_name, backend_or_None)``.

    Auto-fallback to ``"structured-log"`` if the requested backend's
    library is unavailable; logs a one-time WARNING on the fallback.
    """
    if name == "noop":
        return "noop", None
    if name == "structured-log":
        return "structured-log", _StructuredLogBackend()
    if name == "prometheus-client":
        if importlib.util.find_spec("prometheus_client") is None:
            logger.warning(
                "observability.metrics backend=prometheus-client requested but "
                "prometheus_client library not installed; falling back to "
                "structured-log",
            )
            return "structured-log", _StructuredLogBackend()
        try:
            return "prometheus-client", _PrometheusClientBackend()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "observability.metrics prometheus-client init failed (%s); "
                "falling back to structured-log",
                type(exc).__name__,
            )
            return "structured-log", _StructuredLogBackend()
    if name == "statsd":
        if importlib.util.find_spec("statsd") is None:
            logger.warning(
                "observability.metrics backend=statsd requested but "
                "statsd library not installed; falling back to structured-log",
            )
            return "structured-log", _StructuredLogBackend()
        try:
            return "statsd", _StatsdBackend()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "observability.metrics statsd init failed (%s); falling back "
                "to structured-log",
                type(exc).__name__,
            )
            return "structured-log", _StructuredLogBackend()
    # Unknown backend name — log + fall back to structured-log.
    logger.warning(
        "observability.metrics unknown backend=%r; falling back to "
        "structured-log",
        name,
    )
    return "structured-log", _StructuredLogBackend()


# ─── Backend implementations ────────────────────────────────────────────


class _StructuredLogBackend:
    """Emits one JSON line per call on the dedicated metrics logger.

    Operators ship the log line to their metric backend of choice via
    Vector / Fluent Bit / Datadog log forwarder. This is the same
    payload v3.38.0 Agent 4 emitted as the inline fallback.
    """

    def counter(self, name: str, value: float, labels: dict[str, str]) -> None:
        self._emit(name, "counter", value, labels)

    def gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
        self._emit(name, "gauge", value, labels)

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        # buckets is informational only on this backend — recorded in the
        # log line so operators can reconstruct shape if forwarding to a
        # real histogram backend.
        self._emit(name, "histogram", value, labels, buckets=buckets)

    @staticmethod
    def _emit(
        name: str,
        kind: str,
        value: float,
        labels: dict[str, str],
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "metric": name,
            "kind": kind,
            "value": value,
            "labels": labels,
        }
        if buckets is not None:
            payload["buckets"] = list(buckets)
        try:
            line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            safe = {k: str(v) for k, v in labels.items()}
            safe_payload: dict[str, Any] = {
                "metric": name, "kind": kind, "value": value, "labels": safe,
            }
            if buckets is not None:
                safe_payload["buckets"] = list(buckets)
            line = json.dumps(
                safe_payload, sort_keys=True, separators=(",", ":"),
            )
        logger.info("observability_metric %s", line)


class _PrometheusClientBackend:
    """Wraps the ``prometheus_client`` library.

    Counter / Gauge / Histogram objects are cached per metric name (so
    repeated emissions don't re-register and trip
    ``Duplicated timeseries`` errors). The cache is keyed on the metric
    name + the sorted tuple of label keys.
    """

    def __init__(self) -> None:
        # Lazy import — the find_spec gate above already proved the
        # library is importable; we don't catch ImportError here.
        self._pc = importlib.import_module("prometheus_client")
        self._cache_lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[str, ...]], Any] = {}
        self._gauges: dict[tuple[str, tuple[str, ...]], Any] = {}
        self._histograms: dict[tuple[str, tuple[str, ...]], Any] = {}
        # v3.40.0: track which buckets each histogram name was registered with
        # so a second call with DIFFERENT buckets emits a warning AND reuses
        # the first registration (prom-client raises Duplicated timeseries
        # otherwise — see `histogram()` docstring on the public API).
        self._histogram_buckets: dict[tuple[str, tuple[str, ...]], tuple[float, ...] | None] = {}
        try:
            from django.conf import settings

            self._namespace = getattr(
                settings, "OBSERVABILITY_PROMETHEUS_NAMESPACE", "runmycampus",
            )
        except Exception:  # noqa: BLE001
            self._namespace = "runmycampus"

    def _normalize_name(self, name: str) -> str:
        """Prometheus names use ``_`` separators; we accept ``.`` from
        callers and rewrite. The namespace prefix is prepended unless
        the caller already used it.
        """
        normalized = name.replace(".", "_").replace("-", "_")
        if self._namespace and not normalized.startswith(self._namespace + "_"):
            normalized = f"{self._namespace}_{normalized}"
        return normalized

    def _get_counter(self, name: str, label_keys: tuple[str, ...]) -> Any:
        key = (name, label_keys)
        with self._cache_lock:
            obj = self._counters.get(key)
            if obj is None:
                obj = self._pc.Counter(
                    name, f"Counter {name}", labelnames=list(label_keys),
                )
                self._counters[key] = obj
        return obj

    def _get_gauge(self, name: str, label_keys: tuple[str, ...]) -> Any:
        key = (name, label_keys)
        with self._cache_lock:
            obj = self._gauges.get(key)
            if obj is None:
                obj = self._pc.Gauge(
                    name, f"Gauge {name}", labelnames=list(label_keys),
                )
                self._gauges[key] = obj
        return obj

    def _get_histogram(
        self,
        name: str,
        label_keys: tuple[str, ...],
        buckets: tuple[float, ...] | None = None,
    ) -> Any:
        """Return a cached ``prometheus_client.Histogram`` for ``name``.

        First-registration wins on buckets. A subsequent call with a
        DIFFERENT (non-None) ``buckets`` tuple logs a structured WARNING
        and reuses the first registration. None buckets fall back to
        prom-client's defaults (preserves v3.39 behavior).
        """
        key = (name, label_keys)
        with self._cache_lock:
            obj = self._histograms.get(key)
            if obj is None:
                kwargs: dict[str, Any] = {"labelnames": list(label_keys)}
                if buckets is not None:
                    kwargs["buckets"] = tuple(buckets)
                obj = self._pc.Histogram(
                    name, f"Histogram {name}", **kwargs,
                )
                self._histograms[key] = obj
                self._histogram_buckets[key] = (
                    tuple(buckets) if buckets is not None else None
                )
            else:
                # Already registered. If caller asked for a different
                # bucket tuple, warn (do NOT re-register — prom raises).
                first = self._histogram_buckets.get(key)
                if (
                    buckets is not None
                    and tuple(buckets) != (first or ())
                    and first is not None
                ):
                    logger.warning(
                        "observability.metrics histogram=%s bucket_override_ignored "
                        "first_buckets=%s requested_buckets=%s",
                        name, first, tuple(buckets),
                    )
        return obj

    def counter(self, name: str, value: float, labels: dict[str, str]) -> None:
        pname = self._normalize_name(name)
        keys = tuple(sorted(labels.keys()))
        obj = self._get_counter(pname, keys)
        if labels:
            obj.labels(**labels).inc(value)
        else:
            obj.inc(value)

    def gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
        pname = self._normalize_name(name)
        keys = tuple(sorted(labels.keys()))
        obj = self._get_gauge(pname, keys)
        if labels:
            obj.labels(**labels).set(value)
        else:
            obj.set(value)

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        pname = self._normalize_name(name)
        keys = tuple(sorted(labels.keys()))
        obj = self._get_histogram(pname, keys, buckets=buckets)
        if labels:
            obj.labels(**labels).observe(value)
        else:
            obj.observe(value)


class _StatsdBackend:
    """Wraps the ``statsd`` library. Labels are appended DataDog-style
    (``metric.name#tag:value,tag:value``).
    """

    def __init__(self) -> None:
        statsd_mod = importlib.import_module("statsd")
        try:
            from django.conf import settings

            host = getattr(settings, "OBSERVABILITY_METRICS_STATSD_HOST", "") or "localhost"
            port = int(getattr(settings, "OBSERVABILITY_METRICS_STATSD_PORT", 8125))
        except Exception:  # noqa: BLE001
            host, port = "localhost", 8125
        self._client = statsd_mod.StatsClient(host, port)

    @staticmethod
    def _format_with_tags(name: str, labels: dict[str, str]) -> str:
        if not labels:
            return name
        tag_str = ",".join(f"{k}:{v}" for k, v in sorted(labels.items()))
        return f"{name}#{tag_str}"

    def counter(self, name: str, value: float, labels: dict[str, str]) -> None:
        self._client.incr(self._format_with_tags(name, labels), int(value) or 1)

    def gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
        self._client.gauge(self._format_with_tags(name, labels), value)

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        # statsd has no native histogram; map to timing (ms-shaped float).
        # ``buckets`` is silently ignored — statsd aggregates server-side
        # and the operator's statsd→Prom translator picks its own buckets.
        self._client.timing(self._format_with_tags(name, labels), value)


# ─── Public API ─────────────────────────────────────────────────────────


def _coerce_labels(
    labels: dict[str, Any] | None, tags: dict[str, Any] | None,
) -> dict[str, str]:
    """Accept either ``labels=`` (v3.39 canonical) or ``tags=``
    (v3.38 Agent 4 legacy). Sanitize before returning.
    """
    merged: dict[str, Any] = {}
    if tags:
        merged.update(tags)
    if labels:
        merged.update(labels)
    return _sanitize_labels(merged)


def emit_counter(
    name: str,
    value: int | float = 1,
    *,
    labels: dict[str, Any] | None = None,
    tags: dict[str, Any] | None = None,
) -> None:
    """Increment a counter metric. NEVER raises — metric failures log
    WARNING and are swallowed so the calling hot path is unaffected.
    """
    try:
        backend_name, backend = _get_backend()
        if backend is None:  # noop
            return
        cleaned = _coerce_labels(labels, tags)
        backend.counter(str(name), float(value), cleaned)
    except Exception as exc:  # noqa: BLE001 - metrics never break hot path
        logger.warning(
            "observability.metrics emit_counter failed metric=%s err=%s",
            name, type(exc).__name__,
        )


def emit_gauge(
    name: str,
    value: float,
    *,
    labels: dict[str, Any] | None = None,
    tags: dict[str, Any] | None = None,
) -> None:
    """Set a gauge metric. NEVER raises."""
    try:
        backend_name, backend = _get_backend()
        if backend is None:
            return
        cleaned = _coerce_labels(labels, tags)
        backend.gauge(str(name), float(value), cleaned)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "observability.metrics emit_gauge failed metric=%s err=%s",
            name, type(exc).__name__,
        )


def emit_histogram(
    name: str,
    value: float,
    *,
    labels: dict[str, Any] | None = None,
    tags: dict[str, Any] | None = None,
    buckets: tuple[float, ...] | list[float] | None = None,
) -> None:
    """Observe a histogram value (bucketed latency / size / etc.).

    v3.40.0: optional ``buckets`` kwarg lets callers pin a custom
    Prometheus histogram bucket tuple at registration time. Behavior:

    * **prometheus-client backend** — ``buckets`` is passed to
      ``Histogram(name, doc, labelnames, buckets=tuple)`` on FIRST
      registration. The bucket choice is sticky: a subsequent call to
      this metric with a different ``buckets`` tuple emits a WARNING
      (``bucket_override_ignored``) and continues observing into the
      ORIGINAL buckets. This is because prom-client raises
      ``Duplicated timeseries`` if you try to re-register; first-wins
      is the only safe semantics.
    * **structured-log backend** — buckets appear in the JSON line under
      a ``"buckets"`` key (informational; log shippers can reconstruct).
    * **statsd / noop backends** — ``buckets`` is silently ignored
      (statsd aggregates server-side; noop does nothing).

    Falls back to ``statsd.timing`` on the statsd backend and to a
    structured-log line on the log backend. NEVER raises.
    """
    try:
        backend_name, backend = _get_backend()
        if backend is None:
            return
        cleaned = _coerce_labels(labels, tags)
        bucket_tuple: tuple[float, ...] | None
        if buckets is None:
            bucket_tuple = None
        else:
            try:
                bucket_tuple = tuple(float(b) for b in buckets)
            except (TypeError, ValueError):
                bucket_tuple = None
        # Backwards-compat: pre-v3.40 backends accept only 3-arg histogram.
        # All in-tree backends now accept buckets=, but we guard so an
        # operator-extended backend without the kwarg keeps working.
        try:
            backend.histogram(str(name), float(value), cleaned, buckets=bucket_tuple)
        except TypeError:
            backend.histogram(str(name), float(value), cleaned)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "observability.metrics emit_histogram failed metric=%s err=%s",
            name, type(exc).__name__,
        )


# ─── Shutdown / flush ───────────────────────────────────────────────────


def shutdown_metrics_backend() -> None:
    """Flush + close the active metrics backend (best-effort).

    Designed for Celery ``worker_shutdown`` signal AND gunicorn SIGTERM
    via ``atexit``. Statsd's UDP transport is fire-and-forget BUT the
    pystatsd ``StatsClient`` with a pipeline (buffered transport) keeps
    bytes in its socket buffer until ``close()``; the Celery worker
    exiting before the buffer drains causes silent metric loss.

    Behavior by backend:

    * ``statsd`` — calls ``client.close()`` if present, else
      ``client._sock.close()`` if present. Both are wrapped in a guard
      because pystatsd's API surface varies by version.
    * ``prometheus-client`` — no-op. Prom is pull-based; nothing to flush.
    * ``structured-log`` — no-op. Lines went straight to ``logging``.
    * ``noop`` — no-op.

    Idempotent — after the first call, the backend cache is reset so a
    second invocation is a fast no-op-after-cache-clear. NEVER raises;
    a backend whose close() throws is logged at WARNING and swallowed.
    """
    # Snapshot under lock so concurrent emissions don't race the close.
    with _backend_lock:
        if not _backend_cache["resolved"]:
            return
        name = _backend_cache["name"]
        backend = _backend_cache["backend"]
    if backend is None:
        return
    try:
        if name == "statsd":
            client = getattr(backend, "_client", None)
            if client is not None:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
                else:
                    sock = getattr(client, "_sock", None)
                    if sock is not None and hasattr(sock, "close"):
                        sock.close()
                # If the client is a pipeline-style buffered transport,
                # also flush the internal pipe before closing.
                pipe = getattr(client, "_pipe", None)
                if pipe is not None:
                    pipe_close = getattr(pipe, "close", None)
                    if callable(pipe_close):
                        pipe_close()
        # prometheus-client / structured-log / noop: nothing to flush.
    except Exception as exc:  # noqa: BLE001 - best-effort shutdown only
        logger.warning(
            "observability.metrics shutdown backend=%s failed err=%s",
            name, type(exc).__name__,
        )
    finally:
        # Drop the cached backend so a re-import / fork picks a fresh one
        # AND so a second shutdown call short-circuits at the resolved
        # check above.
        with _backend_lock:
            _backend_cache["resolved"] = False
            _backend_cache["name"] = "noop"
            _backend_cache["backend"] = None


# Web-worker exit (gunicorn SIGTERM, uvicorn shutdown, dev `runserver`
# Ctrl-C) — Celery workers register their own hook in
# `apps/observability/celery_signals.py` so the per-process exit path
# always flushes statsd.
atexit.register(shutdown_metrics_backend)


__all__ = [
    "emit_counter",
    "emit_gauge",
    "emit_histogram",
    "shutdown_metrics_backend",
    "_sanitize_labels",
    "_reset_backend_cache",
    "_get_backend",
]
