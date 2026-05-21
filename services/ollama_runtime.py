"""
Best-effort Ollama process reachability before gateway inference.

Does not shell out to ``verify_ollama_live.py`` on each request (that script is for
operators/CI). Instead: probe → optional one-shot ``ollama serve`` → re-probe.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_START_COOLDOWN_KEY = "ai:ollama:auto-start-cooldown"
_START_WAIT_SEC = 2.5
_PROBE_AFTER_START_SEC = 0.4


def _ollama_auto_start_enabled() -> bool:
    if hasattr(settings, "OLLAMA_AUTO_START"):
        return bool(getattr(settings, "OLLAMA_AUTO_START"))
    raw = os.environ.get("OLLAMA_AUTO_START", "")
    if raw.strip():
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    # Default: try on developer hosts; never auto-spawn on cloud deploy.
    if getattr(settings, "RUNNING_TESTS", False):
        return False
    if getattr(settings, "_IS_CLOUD_DEPLOYED", False):
        return False
    return bool(getattr(settings, "DEBUG", False))


def _spawn_ollama_serve() -> bool:
    """Start ``ollama serve`` detached when the CLI exists on this host."""
    exe = shutil.which("ollama")
    if not exe:
        logger.debug("ollama auto-start: ollama binary not on PATH")
        return False
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=sys.platform != "win32",
        )
        logger.info("ollama auto-start: spawned `ollama serve` (%s)", exe)
        return True
    except OSError as exc:
        logger.warning("ollama auto-start: could not spawn serve: %s", exc)
        return False


def _cooldown_active() -> bool:
    try:
        from django.core.cache import cache

        return bool(cache.get(_START_COOLDOWN_KEY))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return False


def _mark_cooldown(seconds: int = 90) -> None:
    try:
        from django.core.cache import cache

        cache.set(_START_COOLDOWN_KEY, True, max(30, int(seconds)))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        pass


def ensure_ollama_reachable(*, force_refresh: bool = False) -> bool:
    """
    Return True when Ollama answers on the resolved base URL.

    When ``OLLAMA_AUTO_START`` is enabled and the daemon is down, attempts a single
    background ``ollama serve`` per cooldown window, then re-probes.
    """
    from apps.portal.ai_provider import (
        _probe_ollama_base,
        invalidate_ollama_connection_cache,
        resolve_ollama_connection,
    )

    if force_refresh:
        invalidate_ollama_connection_cache()

    conn = resolve_ollama_connection(force_refresh=force_refresh)
    base = str(conn.get("base_url") or "").strip()
    if not base:
        return False

    ok, _latency = _probe_ollama_base(base)
    if ok:
        return True

    if not _ollama_auto_start_enabled() or _cooldown_active():
        return False

    _mark_cooldown()
    if not _spawn_ollama_serve():
        return False

    time.sleep(_PROBE_AFTER_START_SEC)
    deadline = time.monotonic() + _START_WAIT_SEC
    while time.monotonic() < deadline:
        invalidate_ollama_connection_cache()
        conn = resolve_ollama_connection(force_refresh=True)
        base = str(conn.get("base_url") or "").strip()
        ok, _latency = _probe_ollama_base(base)
        if ok:
            logger.info("ollama auto-start: reachable at %s", base)
            return True
        time.sleep(0.35)

    logger.warning("ollama auto-start: serve spawned but %s still not reachable", base)
    return False


def operator_posture_summary() -> dict[str, Any]:
    """Lightweight dict for logging / diagnostics (not a subprocess verify script)."""
    from apps.portal.ai_provider import probe_ai_provider_reachable, resolve_ollama_connection

    conn = resolve_ollama_connection()
    health = probe_ai_provider_reachable()
    return {
        "auto_start_enabled": _ollama_auto_start_enabled(),
        "base_url": conn.get("base_url"),
        "discovery_source": conn.get("discovery_source"),
        "reachable": bool(health.get("reachable")),
        "degraded": bool(health.get("degraded")),
    }
