"""LiteLLM multi-model failover within the cloud tier (<50ms target to secondary)."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def litellm_model_chain(*, model_key: str | None = None) -> tuple[str, ...]:
    """Ordered model list: explicit key, env chain, then primary default."""
    if model_key:
        return (str(model_key).strip(),)

    raw = (os.environ.get("LITELLM_MODEL_CHAIN") or "").strip()
    if raw:
        parts = tuple(m.strip() for m in raw.split(",") if m.strip())
        if parts:
            return parts

    from services.ai_deployment_posture import litellm_model

    primary = litellm_model()
    fallback = (os.environ.get("LITELLM_MODEL_FALLBACK") or "").strip()
    if fallback and fallback != primary:
        return (primary, fallback)
    return (primary,)
