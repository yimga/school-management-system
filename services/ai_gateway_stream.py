"""Streaming LiteLLM gateway (v4.00.0).

Why this lives next to ``services.ai_gateway`` instead of inside it:
  * The existing ``_call_litellm`` is the non-streaming load-bearing path for
    the audit/fallback/structured-output contract. Touching it risks the
    13 zero-tolerance scanners that depend on its current shape.
  * Streaming has a different error contract (chunked decode failures should
    NOT take down the whole gateway).

Public surface:
  * ``stream_litellm(prompt, viewport='A', metadata=..., on_chunk=...)``
    — generator yielding (chunk_text, meta) tuples.
  * ``stream_to_channel_group(group_name, prompt, viewport='A', ...)``
    — Channels group broadcast loop for the WS UI mount client.

Both honor ``services.prompt_shaping`` for viewport-aware token stripping.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from services.ai_deployment_posture import (
    litellm_api_key,
    litellm_model,
    litellm_proxy_url,
)
from services.prompt_shaping import ShapedPrompt, shape

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 30


def _build_payload(shaped: ShapedPrompt, model: str) -> bytes:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": msg} for msg in shaped.system_messages
    ]
    messages.append({"role": "user", "content": shaped.prompt})
    payload = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": shaped.max_completion_tokens,
        "temperature": 0.3,
        "stream": True,
    }
    return json.dumps(payload).encode("utf-8")


def _parse_sse_chunk(raw_line: bytes) -> tuple[str | None, bool]:
    """Parse one SSE line. Returns (chunk_text or None, done)."""
    line = raw_line.decode("utf-8", errors="replace").strip()
    if not line or not line.startswith("data:"):
        return None, False
    data = line[len("data:"):].strip()
    if data == "[DONE]":
        return None, True
    try:
        envelope = json.loads(data)
    except json.JSONDecodeError:
        return None, False
    choices = envelope.get("choices") or []
    if not choices:
        return None, False
    delta = choices[0].get("delta") or {}
    chunk = delta.get("content") or ""
    return (chunk or None), False


def stream_litellm(
    prompt: str,
    *,
    viewport: str = "A",
    metadata: dict[str, Any] | None = None,
    model_key: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    on_chunk: Callable[[str], None] | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Stream a LiteLLM completion as (chunk_text, meta) tuples.

    Yields nothing and silently exits when LiteLLM is unreachable / not configured.
    The caller is expected to fall back to the non-streaming path or rules engine.
    """
    proxy = litellm_proxy_url()
    if not proxy:
        logger.debug("ai_gateway_stream.no_proxy_configured")
        return
    shaped = shape(prompt, viewport=viewport)
    model = litellm_model(model_key=model_key)
    url = (
        f"{proxy}/v1/chat/completions"
        if "/v1/" not in proxy
        else f"{proxy}/chat/completions"
    )
    if not url.startswith("http"):
        url = f"https://{url}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-RMC-Viewport": shaped.viewport,
    }
    api_key = litellm_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url,
        data=_build_payload(shaped, model),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            for raw_line in resp:
                chunk, done = _parse_sse_chunk(raw_line)
                if chunk is not None:
                    if on_chunk is not None:
                        try:
                            on_chunk(chunk)
                        except Exception as exc:  # noqa: BLE001 — observer must not break stream
                            logger.debug("stream_litellm.on_chunk_failed: %s", exc)
                    yield chunk, {
                        "provider": "litellm",
                        "model": model,
                        "viewport": shaped.viewport,
                    }
                if done:
                    return
    except urllib.error.HTTPError as exc:
        logger.warning("stream_litellm.http %s: %s", exc.code, url)
        return
    except urllib.error.URLError as exc:
        logger.debug("stream_litellm.unreachable: %s", getattr(exc, "reason", exc))
        return
    except TimeoutError:
        logger.warning("stream_litellm.timeout")
        return


def stream_to_channel_group(
    group_name: str,
    prompt: str,
    *,
    viewport: str = "A",
    metadata: dict[str, Any] | None = None,
    model_key: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Stream a completion into a Channels group so the WS UI mount client
    can render fragments as they arrive.

    Returns a summary dict ``{chunks: int, viewport: str, completed: bool}``.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
    except ImportError:
        logger.warning("stream_to_channel_group.channels_missing")
        return {"chunks": 0, "viewport": viewport, "completed": False}
    layer = get_channel_layer()
    if layer is None:
        return {"chunks": 0, "viewport": viewport, "completed": False}
    chunks = 0
    send = async_to_sync(layer.group_send)
    for chunk, meta in stream_litellm(
        prompt,
        viewport=viewport,
        metadata=metadata,
        model_key=model_key,
    ):
        chunks += 1
        send(group_name, {
            "type": "ai.stream.chunk",
            "session_id": session_id,
            "chunk": chunk,
            "meta": meta,
        })
    send(group_name, {
        "type": "ai.stream.done",
        "session_id": session_id,
        "chunks": chunks,
    })
    return {"chunks": chunks, "viewport": viewport, "completed": True}
