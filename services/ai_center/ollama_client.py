"""Governed Ollama HTTP client for AI Center (circuit breaker, no prompt logging by default)."""

from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class OllamaAICenterClient:
    """Thin Ollama /api/chat client with failure counting."""

    def __init__(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def _base_url(self) -> str:
        raw = getattr(settings, "OLLAMA_BASE_URL", None) or "http://127.0.0.1:11434"
        return str(raw).rstrip("/")

    def _model(self) -> str:
        return str(getattr(settings, "OLLAMA_MODEL", "ai-center-master") or "ai-center-master")

    def _timeout(self) -> int:
        try:
            return max(3, min(int(getattr(settings, "AI_CENTER_TIMEOUT_SECONDS", 30)), 120))
        except (TypeError, ValueError):
            return 30

    def circuit_open(self) -> bool:
        return time.monotonic() < self._open_until

    def _trip_circuit(self) -> None:
        self._failures += 1
        if self._failures >= 3:
            self._open_until = time.monotonic() + 60.0

    def _reset_circuit(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def enabled(self) -> bool:
        if not bool(getattr(settings, "AI_GATEWAY_ENABLED", True)):
            return False
        provider = str(getattr(settings, "AI_GATEWAY_PROVIDER", "ollama") or "ollama").lower()
        return provider == "ollama"

    def generate(self, *, system: str, user: str) -> dict[str, Any]:
        """
        Returns {"ok": bool, "text": str, "error": str|None, "provider": "ollama"|"disabled"}.
        Never logs prompt bodies unless AI_CENTER_LOG_PROMPTS=True.
        """
        if not self.enabled():
            return {"ok": False, "text": "", "error": "gateway_disabled", "provider": "disabled"}
        if self.circuit_open():
            return {"ok": False, "text": "", "error": "circuit_open", "provider": "ollama"}

        if bool(getattr(settings, "AI_CENTER_LOG_PROMPTS", False)):
            logger.debug("ollama prompt system_len=%s user_len=%s", len(system), len(user))
        else:
            logger.debug("ollama request model=%s", self._model())

        try:
            import urllib.error
            import urllib.request

            payload = {
                "model": self._model(),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.0},
            }
            import json

            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url()}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout()) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            message = data.get("message") or {}
            text = (message.get("content") or "").strip()
            self._reset_circuit()
            return {"ok": bool(text), "text": text, "error": None, "provider": "ollama"}
        except Exception as exc:
            self._trip_circuit()
            logger.warning("ollama ai_center client error: %s", type(exc).__name__)
            return {"ok": False, "text": "", "error": type(exc).__name__, "provider": "ollama"}
