"""
Pluggable embedding provider: Ollama or OpenAI-compatible endpoint. Used by AIMemoryService
and semantic search. Configure via AI_EMBEDDING_BACKEND=ollama|openai_compatible.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str, *, max_tokens: int = 8192) -> list[float] | None:
        pass

    def embed_batch(self, texts: list[str], *, max_tokens: int = 8192) -> list[list[float] | None]:
        return [self.embed(t[:max_tokens], max_tokens=max_tokens) for t in texts]


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str, model: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed(self, text: str, *, max_tokens: int = 8192) -> list[float] | None:
        if not text:
            return None
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": self.model, "prompt": text[:max_tokens]}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            emb = data.get("embedding")
            if isinstance(emb, list) and emb:
                return [float(x) for x in emb]
        except urllib.error.URLError as e:
            logger.debug("Ollama embeddings failed: %s", e.reason)
        except Exception as e:
            logger.warning("Ollama embeddings error: %s", e)
        return None


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(self, endpoint: str, model: str, api_key: str | None = None):
        self.endpoint = endpoint.rstrip("/")
        if "/v1/embeddings" not in self.endpoint and "/embeddings" not in self.endpoint:
            self.endpoint = f"{self.endpoint}/v1/embeddings"
        self.model = model
        self.api_key = api_key or ""

    def embed(self, text: str, *, max_tokens: int = 8192) -> list[float] | None:
        if not text:
            return None
        payload = {"model": self.model, "input": text[:max_tokens]}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data") or []
            if items and isinstance(items[0].get("embedding"), list):
                return [float(x) for x in items[0]["embedding"]]
        except urllib.error.URLError as e:
            logger.debug("OpenAI-compatible embeddings failed: %s", getattr(e, "reason", e))
        except Exception as e:
            logger.warning("OpenAI-compatible embeddings error: %s", e)
        return None


def get_embedding_provider() -> EmbeddingProvider:
    backend = (
        getattr(settings, "AI_EMBEDDING_BACKEND", None)
        or os.environ.get("AI_EMBEDDING_BACKEND")
        or "ollama"
    ).strip().lower()
    if backend == "openai_compatible":
        endpoint = (
            getattr(settings, "AI_EMBEDDING_ENDPOINT", None)
            or os.environ.get("AI_EMBEDDING_ENDPOINT")
            or ""
        ).strip()
        model = (
            getattr(settings, "AI_EMBEDDING_MODEL", None)
            or os.environ.get("AI_EMBEDDING_MODEL")
            or "text-embedding-3-small"
        ).strip()
        api_key = (
            getattr(settings, "AI_EMBEDDING_API_KEY", None)
            or os.environ.get("AI_EMBEDDING_API_KEY")
            or ""
        ).strip()
        if not endpoint:
            logger.warning("AI_EMBEDDING_ENDPOINT not set; falling back to Ollama")
            backend = "ollama"
        else:
            return OpenAICompatibleEmbeddingProvider(endpoint, model, api_key or None)
    if backend == "ollama" or not backend:
        try:
            from services.inference import _get_regional_config
            base_url, _, _ = _get_regional_config()
        except Exception:
            try:
                from apps.portal.ai_provider import resolve_ollama_connection

                base_url = resolve_ollama_connection().get("base_url") or "http://127.0.0.1:11434"
            except Exception:
                base_url = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434").strip().rstrip("/")
                if base_url.endswith("/api/generate"):
                    base_url = base_url.rsplit("/", 2)[0]
        model = getattr(settings, "AI_EMBEDDING_OLLAMA_MODEL", None) or os.environ.get("AI_EMBEDDING_OLLAMA_MODEL") or "nomic-embed-text"
        return OllamaEmbeddingProvider(base_url, model)
    return OllamaEmbeddingProvider("http://localhost:11434", "nomic-embed-text")


def embedding_provider_descriptor(provider: EmbeddingProvider | None = None) -> str:
    """Return a stable backend:model identifier for persisted vectors."""
    provider = provider or get_embedding_provider()
    model = str(getattr(provider, "model", "") or "").strip()
    if isinstance(provider, OpenAICompatibleEmbeddingProvider):
        backend = "openai_compatible"
    elif isinstance(provider, OllamaEmbeddingProvider):
        backend = "ollama"
    else:
        backend = provider.__class__.__name__.lower()
    return f"{backend}:{model}" if model else backend
