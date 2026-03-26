"""
Guarded Ollama model pulls: allowlisted model IDs only, argv list (no shell), timeouts.

Used by management command sync_ollama_models and (optionally) Celery beat.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Iterable

from django.conf import settings

logger = logging.getLogger(__name__)

# Ollama library names: alnum, dots, colons (tags), slashes, hyphens, plus, @ for some registries.
_OLLAMA_MODEL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/+\-@]{0,255}$")


def is_allowed_ollama_model_id(model_id: str) -> bool:
    if not model_id or not isinstance(model_id, str):
        return False
    s = model_id.strip()
    if len(s) > 256:
        return False
    return _OLLAMA_MODEL_ID_RE.fullmatch(s) is not None


def filtered_models(ids: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        mid = (raw or "").strip()
        if not mid or mid in seen:
            continue
        if not is_allowed_ollama_model_id(mid):
            logger.warning("Skipping disallowed Ollama model id (allowlist): %r", mid[:80])
            continue
        seen.add(mid)
        out.append(mid)
    return out


def collect_ollama_models_for_sync(*, include_registry: bool) -> list[str]:
    """Env-driven chat + embedding models, optional extras, optional AIModelRegistry rows."""
    candidates: list[str] = []
    om = (
        os.environ.get("OLLAMA_MODEL")
        or getattr(settings, "OLLAMA_MODEL", None)
        or "llama3"
    )
    candidates.append(str(om).strip())
    backend = (os.environ.get("AI_EMBEDDING_BACKEND") or "ollama").strip().lower()
    if backend in ("ollama", ""):
        emb = (
            os.environ.get("AI_EMBEDDING_OLLAMA_MODEL")
            or getattr(settings, "AI_EMBEDDING_OLLAMA_MODEL", None)
            or "nomic-embed-text"
        )
        candidates.append(str(emb).strip())
    extra = os.environ.get("OLLAMA_SYNC_EXTRA_MODELS", "").strip()
    if extra:
        candidates.extend(x.strip() for x in extra.split(",") if x.strip())
    if include_registry:
        try:
            from apps.siteconfig.models import AIModelRegistry

            for row in AIModelRegistry.objects.filter(is_active=True).only("model_id"):
                mid = (getattr(row, "model_id", None) or "").strip()
                if mid:
                    candidates.append(mid)
        except Exception as e:
            logger.warning("AIModelRegistry read failed during model collect: %s", e)
    return filtered_models(candidates)


def run_ollama_pull(
    model_id: str, *, ollama_bin: str, timeout: int
) -> tuple[int, str]:
    """
    Run `ollama pull <model_id>`. model_id must already pass is_allowed_ollama_model_id.
    Returns (returncode, tail of combined stdout/stderr).
    """
    if not is_allowed_ollama_model_id(model_id):
        return 125, "model_id failed allowlist"
    cmd = [ollama_bin, "pull", model_id]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "ollama executable not found (set OLLAMA_CLI_PATH or install Ollama)"
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-12000:]
    return proc.returncode, tail
