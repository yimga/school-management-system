"""
Ollama model lifecycle: tag checks, optional pull, double-buffered active model pointer.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_ACTIVE_MODEL_KEY = "ai:ollama:active_model"
_STAGING_MODEL_KEY = "ai:ollama:staging_model"


class OllamaModelLifecycleManager:
    """Operator-side model refresh with safe rollback on failure."""

    def __init__(self, *, endpoint: str | None = None, target_model: str | None = None) -> None:
        self.endpoint = (
            endpoint
            or getattr(settings, "OLLAMA_ENDPOINT", None)
            or os.environ.get("OLLAMA_ENDPOINT")
            or "http://localhost:11434"
        ).strip().rstrip("/")
        if self.endpoint.endswith("/api/generate"):
            self.endpoint = self.endpoint.rsplit("/", 2)[0]
        self.target_model = (
            target_model
            or getattr(settings, "OLLAMA_MODEL", None)
            or os.environ.get("OLLAMA_MODEL")
            or "llama3"
        ).strip()

    def _get_json(self, path: str, *, timeout: float = 10.0) -> dict[str, Any]:
        url = f"{self.endpoint}{path}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any], *, timeout: float = 120.0) -> dict[str, Any]:
        url = f"{self.endpoint}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}

    def list_local_models(self) -> list[str]:
        try:
            body = self._get_json("/api/tags", timeout=8.0)
            models = body.get("models") or []
            return [str(m.get("name", "")).strip() for m in models if m.get("name")]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Ollama tags check failed: %s", exc)
            return []

    def active_model(self) -> str:
        cached = cache.get(_ACTIVE_MODEL_KEY)
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
        return self.target_model

    def check_and_update_model(self, *, pull_if_missing: bool = True) -> dict[str, Any]:
        """
        Verify target model exists locally; optionally pull; hot-swap active pointer on success.
        """
        started = time.perf_counter()
        report: dict[str, Any] = {
            "endpoint": self.endpoint,
            "target_model": self.target_model,
            "previous_active": self.active_model(),
            "swapped": False,
            "pulled": False,
            "healthy": False,
            "error": None,
        }
        try:
            local = self.list_local_models()
            report["local_models"] = local
            has_target = any(
                m == self.target_model or m.startswith(f"{self.target_model}:")
                for m in local
            )
            if not has_target and pull_if_missing:
                cache.set(_STAGING_MODEL_KEY, self.target_model, timeout=3600)
                self._post_json("/api/pull", {"name": self.target_model, "stream": False}, timeout=600.0)
                report["pulled"] = True
                local = self.list_local_models()
                has_target = any(
                    m == self.target_model or m.startswith(f"{self.target_model}:")
                    for m in local
                )
            if has_target and self._smoke_test(self.target_model):
                cache.set(_ACTIVE_MODEL_KEY, self.target_model, timeout=86400 * 7)
                report["swapped"] = report["previous_active"] != self.target_model
                report["healthy"] = True
            else:
                report["error"] = "model_unavailable_or_smoke_failed"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            report["error"] = str(exc)
            logger.error("Ollama lifecycle update failed; keeping active model: %s", exc)
        report["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        report["active_model"] = self.active_model()
        return report

    def _smoke_test(self, model: str) -> bool:
        try:
            body = self._post_json(
                "/api/generate",
                {"model": model, "prompt": "Reply with OK only.", "stream": False},
                timeout=30.0,
            )
            return bool((body.get("response") or "").strip())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return False

    def rollback_to_previous(self) -> str:
        """On failed upgrade, revert active pointer to staging/previous."""
        prev = cache.get(_STAGING_MODEL_KEY) or self.target_model
        cache.set(_ACTIVE_MODEL_KEY, prev, timeout=86400 * 7)
        return str(prev)
