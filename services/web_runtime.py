"""Resource-aware Gunicorn sizing for the web service.

The web dyno keeps crashing on Render not because the tier is too small but
because Gunicorn was statically sized: too many workers for the container's RAM
(→ OOM kill → 502), no worker recycling (slow memory growth → OOM), and no
preload (each worker re-imports the heavy app → ~2× RAM). This module turns the
process into a *self-sizing* one: it reads the container's REAL CPU/RAM
allocation (cgroup-aware, via :mod:`services.edge_hardware`) plus the database
connection budget, and recommends a worker/thread/recycle plan that fits.

Binding constraints, smallest wins:
  * memory   — ``(mem_mb - headroom) / per_worker_mb``  (anti-OOM, the usual one)
  * cpu      — ``2 * effective_cpu + 1``                (Gunicorn's classic rule)
  * db_conns — ``DB_MAX_APP_CONNECTIONS / threads``     (anti "too many connections")

Everything is env-configurable (no hardcoding); an explicit ``GUNICORN_WORKERS``
or ``GUNICORN_AUTOSCALE=0`` fully bypasses autoscaling. Pure stdlib so
``config/gunicorn.conf.py`` can import it before Django is configured.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Mapping

_MB = 1024 * 1024  # magic-number-allow: bytes-per-mebibyte

# Defaults — every one is an env override key's fallback, tuned for the
# RunMyCampus web app (a heavy multi-tenant Django process under gthread).
_DEFAULT_PER_WORKER_MB = 600  # magic-number-allow: measured gthread worker RSS estimate (MB)
_DEFAULT_MEM_HEADROOM_MB = 400  # magic-number-allow: master + OS + redis-client reserve (MB)
_DEFAULT_MAX_WORKERS = 8  # Gunicorn's classic sane upper bound
_DEFAULT_THREADS = 4
_DEFAULT_SSE_RESERVE = 2
_DEFAULT_MAX_REQUESTS = 400  # magic-number-allow: per-worker recycle budget (bounds memory growth)
_DEFAULT_MAX_REQUESTS_JITTER_RATIO = 0.2
_DEFAULT_TIMEOUT = 120  # magic-number-allow: gunicorn worker timeout (seconds)
_DEFAULT_GRACEFUL_TIMEOUT = 30
_CPU_WORKER_MULTIPLIER = 2.0
_CPU_WORKER_ADD = 1


@dataclass(frozen=True)
class WebRuntimePlan:
    workers: int
    threads: int
    worker_class: str
    timeout: int
    graceful_timeout: int
    max_requests: int
    max_requests_jitter: int
    preload_app: bool
    worker_tmp_dir: str | None
    rationale: dict


def _bool_env(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = (env.get(key) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    match = re.match(r"\s*(-?\d+)", raw)
    return int(match.group(1)) if match else default


def _detect(effective_cpu: float | None, memory_bytes: int | None) -> tuple[float, int]:
    """Resolve the container's REAL cpu/ram allocation (cgroup-aware)."""
    if effective_cpu is not None and memory_bytes is not None:
        return float(effective_cpu), int(memory_bytes)
    cpu, mem = effective_cpu, memory_bytes
    try:
        from services.edge_hardware import (
            effective_cpu_count,
            effective_memory_bytes,
        )

        if cpu is None:
            cpu = effective_cpu_count()[0]
        if mem is None:
            mem = effective_memory_bytes()[0]
    except Exception:  # noqa: BLE001 - detection must never break process boot
        pass
    return float(cpu or 1.0), int(mem or 0)


def _resolve_worker_tmp_dir(env: Mapping[str, str]) -> str | None:
    explicit = (env.get("GUNICORN_WORKER_TMP_DIR") or "").strip()
    if explicit:
        return explicit
    # Prefer a memory-backed tmp dir for Gunicorn's worker heartbeat file:
    # on container disk the heartbeat can lag and trip spurious WORKER TIMEOUT
    # kills (→ 502s). /dev/shm is RAM, so the heartbeat is always fast.
    shm = "/dev/shm"
    try:
        if os.path.isdir(shm) and os.access(shm, os.W_OK):
            return shm
    except OSError:
        pass
    return None


def plan_web_runtime(
    env: Mapping[str, str] | None = None,
    *,
    effective_cpu: float | None = None,
    memory_bytes: int | None = None,
) -> WebRuntimePlan:
    """Compute a resource-aware Gunicorn plan.

    Precedence for the worker count:
      1. ``GUNICORN_WORKERS`` (explicit integer) — pins it, no autoscaling.
      2. ``GUNICORN_AUTOSCALE=0`` — falls back to ``WEB_CONCURRENCY`` (or 1).
      3. otherwise — min(memory, cpu, db-connection) budget, capped by
         ``GUNICORN_MAX_WORKERS``.

    ``effective_cpu`` / ``memory_bytes`` may be injected (used by tests);
    otherwise they are detected from the container's cgroup limits.
    """
    env = os.environ if env is None else env
    cpu, mem_bytes = _detect(effective_cpu, memory_bytes)
    memory_mb = int(mem_bytes / _MB) if mem_bytes else 0

    worker_class = (env.get("GUNICORN_WORKER_CLASS") or "gthread").strip() or "gthread"
    threads = max(1, _int_env(env, "GUNICORN_THREADS", _DEFAULT_THREADS))
    # gthread pins one thread per live SSE stream; keep a reserve so /health/
    # and normal requests always have a free thread (mirrors sse_wsgi_limits).
    if worker_class == "gthread":
        reserve = _int_env(env, "SSE_THREAD_RESERVE", _DEFAULT_SSE_RESERVE)
        threads = max(threads, reserve + 1)

    per_worker_mb = max(1, _int_env(env, "GUNICORN_PER_WORKER_MB", _DEFAULT_PER_WORKER_MB))
    headroom_mb = max(0, _int_env(env, "GUNICORN_MEM_HEADROOM_MB", _DEFAULT_MEM_HEADROOM_MB))
    max_workers = max(1, _int_env(env, "GUNICORN_MAX_WORKERS", _DEFAULT_MAX_WORKERS))
    db_budget = _int_env(env, "DB_MAX_APP_CONNECTIONS", 0)  # 0 → don't bound on connections

    mem_workers = None
    if memory_mb > 0:
        mem_workers = max(1, (memory_mb - headroom_mb) // per_worker_mb)
    cpu_workers = max(1, math.floor(cpu * _CPU_WORKER_MULTIPLIER + _CPU_WORKER_ADD))
    conn_workers = None
    if db_budget > 0:
        conn_workers = max(1, db_budget // max(1, threads))

    autoscale = _bool_env(env, "GUNICORN_AUTOSCALE", True)
    explicit_workers = _int_env(env, "GUNICORN_WORKERS", 0)

    if explicit_workers > 0:
        workers = explicit_workers
        decided_by = "explicit_workers"
    elif not autoscale:
        workers = max(1, _int_env(env, "WEB_CONCURRENCY", 1))
        decided_by = "web_concurrency"
    else:
        candidates = {"cpu": cpu_workers}
        if mem_workers is not None:
            candidates["memory"] = mem_workers
        if conn_workers is not None:
            candidates["db_connections"] = conn_workers
        decided_by = min(candidates, key=lambda k: candidates[k])
        workers = max(1, min(min(candidates.values()), max_workers))

    timeout = max(1, _int_env(env, "GUNICORN_TIMEOUT", _DEFAULT_TIMEOUT))
    graceful_timeout = max(1, _int_env(env, "GUNICORN_GRACEFUL_TIMEOUT", _DEFAULT_GRACEFUL_TIMEOUT))
    max_requests = max(0, _int_env(env, "GUNICORN_MAX_REQUESTS", _DEFAULT_MAX_REQUESTS))
    jitter_default = (
        int(max_requests * _DEFAULT_MAX_REQUESTS_JITTER_RATIO) if max_requests else 0
    )
    max_requests_jitter = max(
        0, _int_env(env, "GUNICORN_MAX_REQUESTS_JITTER", jitter_default)
    )
    preload_app = _bool_env(env, "GUNICORN_PRELOAD", True)
    worker_tmp_dir = _resolve_worker_tmp_dir(env)

    rationale = {
        "effective_cpu": round(float(cpu), 2),
        "memory_mb": memory_mb,
        "per_worker_mb": per_worker_mb,
        "headroom_mb": headroom_mb,
        "cpu_workers": cpu_workers,
        "mem_workers": mem_workers,
        "conn_workers": conn_workers,
        "max_workers": max_workers,
        "decided_by": decided_by,
        "autoscale": autoscale,
    }
    return WebRuntimePlan(
        workers=workers,
        threads=threads,
        worker_class=worker_class,
        timeout=timeout,
        graceful_timeout=graceful_timeout,
        max_requests=max_requests,
        max_requests_jitter=max_requests_jitter,
        preload_app=preload_app,
        worker_tmp_dir=worker_tmp_dir,
        rationale=rationale,
    )
