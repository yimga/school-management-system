"""Token-by-token streaming for the AI gateway — v3.59.2 (2026-05-22).

Sits beside ``services.ai_gateway`` as a non-intrusive streaming sibling.
The existing ``ai_gateway.invoke()`` keeps its single-shot ``(text, metadata)``
contract; this module adds generator-yielding equivalents that surface chunks
as they arrive from the provider's streaming API.

Surface:
    - ``stream_ollama(prompt, metadata)``  — Ollama ``/api/chat`` (NDJSON)
    - ``stream_litellm(prompt, metadata)`` — LiteLLM OpenAI-style SSE
    - ``invoke_stream(task_type, prompt, *, metadata, user_query)`` — picks
      the best available streaming backend per the resolved tier list. Yields
      ``("chunk", text)`` tuples, then exactly ONE ``("done", metadata)`` tuple
      with provider/posture_mode/request_id fields. On any error, yields one
      ``("error", {"code": ...})`` tuple followed by a final ``("done", {...})``
      so the consumer can always close cleanly.

Wire-protocol contract: callers (the SSE view) translate these tuples to
SSE frames. The gateway tuples are deliberately framework-agnostic so the
same generator can power WebSocket or chunked-JSON consumers later.

Graceful fallback: if a provider isn't streaming-capable (or fails), the
generator emits a single ("chunk", full_reply) using a non-stream call,
then ("done", ...). The consumer experiences the same shape either way.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Iterator

from django.conf import settings

logger = logging.getLogger(__name__)


# Hard ceiling — no streaming reply ever exceeds this. Defends against runaway
# providers and gives the SSE view a bounded loop.
_STREAM_MAX_CHARS = 16_000
_STREAM_DEFAULT_TIMEOUT = 60.0


def _resolve_timeout(metadata: dict[str, Any] | None, default: float = _STREAM_DEFAULT_TIMEOUT) -> float:
    if metadata and "timeout_sec" in metadata:
        try:
            return float(metadata["timeout_sec"])
        except (TypeError, ValueError):
            pass
    return default


# ----------------------------------------------------------------------
# Ollama streaming — `/api/chat` with `stream: true` returns NDJSON.
# Each line is a JSON object with a `message.content` chunk; final line has
# `done: true`. We yield the text chunks as they arrive.
# ----------------------------------------------------------------------
def stream_ollama(
    prompt: str,
    metadata: dict[str, Any] | None = None,
) -> Iterator[tuple[str, Any]]:
    base = (
        getattr(settings, "OLLAMA_BASE_URL", None)
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    ).rstrip("/")
    model = (
        getattr(settings, "OLLAMA_MODEL", None)
        or os.environ.get("OLLAMA_MODEL")
        or "llama3.1"
    ).strip()

    url = f"{base}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "options": {"temperature": 0.3},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    md_final = {"provider": "ollama", "tier": "ollama", "model": model, "posture_mode": "live_local"}

    chars_emitted = 0
    try:
        with urllib.request.urlopen(req, timeout=_resolve_timeout(metadata)) as resp:
            for raw_line in resp:
                if not raw_line:
                    continue
                try:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                except (AttributeError, UnicodeDecodeError):
                    continue
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Ollama chunk shape: {"message": {"role": "assistant", "content": "..."}, "done": false}
                # Final tick:        {"message": {...}, "done": true, "total_duration": ...}
                msg = obj.get("message") or {}
                text = msg.get("content") or ""
                if text:
                    chars_emitted += len(text)
                    if chars_emitted > _STREAM_MAX_CHARS:
                        yield ("chunk", text[: _STREAM_MAX_CHARS - (chars_emitted - len(text))])
                        break
                    yield ("chunk", text)
                if obj.get("done"):
                    break
    except urllib.error.HTTPError as e:
        logger.warning("ollama stream HTTP error %s: %s", e.code, url)
        yield ("error", {"code": f"http_{e.code}", "provider": "ollama"})
        yield ("done", {**md_final, "error": f"http_{e.code}"})
        return
    except urllib.error.URLError as e:
        logger.debug("ollama stream request failed: %s", getattr(e, "reason", e))
        yield ("error", {"code": "unavailable", "provider": "ollama"})
        yield ("done", {**md_final, "posture_mode": "unavailable", "error": "unavailable"})
        return
    except TimeoutError:
        yield ("error", {"code": "timeout", "provider": "ollama"})
        yield ("done", {**md_final, "error": "timeout"})
        return
    except Exception:  # noqa: BLE001 — provider unstable; never propagate
        logger.warning("ollama stream unexpected failure", exc_info=True)
        yield ("error", {"code": "unexpected", "provider": "ollama"})
        yield ("done", {**md_final, "error": "unexpected"})
        return

    yield ("done", md_final)


# ----------------------------------------------------------------------
# LiteLLM streaming — OpenAI-style SSE (`stream: true`). The proxy emits
# `data: {json}\n\n` frames where `choices[0].delta.content` is the chunk.
# A final `data: [DONE]` line terminates the stream.
# ----------------------------------------------------------------------
def stream_litellm(
    prompt: str,
    metadata: dict[str, Any] | None = None,
    model_key: str | None = None,
) -> Iterator[tuple[str, Any]]:
    proxy_url = (
        getattr(settings, "LITELLM_PROXY_URL", None)
        or os.environ.get("LITELLM_PROXY_URL")
        or ""
    ).strip().rstrip("/")
    if not proxy_url:
        yield ("error", {"code": "not_configured", "provider": "litellm"})
        yield ("done", {"provider": "litellm", "posture_mode": "unavailable", "error": "LITELLM_PROXY_URL not set"})
        return

    model = (
        model_key
        or getattr(settings, "LITELLM_MODEL", None)
        or os.environ.get("LITELLM_MODEL")
        or "gpt-3.5-turbo"
    ).strip()
    url = f"{proxy_url}/v1/chat/completions" if "/v1/" not in proxy_url else f"{proxy_url}/chat/completions"
    if not url.startswith("http"):
        url = f"https://{url}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.3,
        "stream": True,
    }
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    api_key = (
        getattr(settings, "LITELLM_API_KEY", None)
        or os.environ.get("LITELLM_API_KEY")
        or ""
    ).strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    md_final = {"provider": "litellm", "tier": "litellm", "model": model, "posture_mode": "live_cloud"}

    chars_emitted = 0
    try:
        with urllib.request.urlopen(req, timeout=_resolve_timeout(metadata)) as resp:
            for raw_line in resp:
                if not raw_line:
                    continue
                try:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                except (AttributeError, UnicodeDecodeError):
                    continue
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    obj = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                # OpenAI-style chunk: {"choices":[{"delta":{"content":"..."}, "finish_reason":null}]}
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0] or {}).get("delta") or {}
                text = delta.get("content") or ""
                if text:
                    chars_emitted += len(text)
                    if chars_emitted > _STREAM_MAX_CHARS:
                        yield ("chunk", text[: _STREAM_MAX_CHARS - (chars_emitted - len(text))])
                        break
                    yield ("chunk", text)
    except urllib.error.HTTPError as e:
        logger.warning("litellm stream HTTP error %s: %s", e.code, url)
        yield ("error", {"code": f"http_{e.code}", "provider": "litellm"})
        yield ("done", {**md_final, "error": f"http_{e.code}"})
        return
    except urllib.error.URLError as e:
        logger.debug("litellm stream request failed: %s", getattr(e, "reason", e))
        yield ("error", {"code": "unavailable", "provider": "litellm"})
        yield ("done", {**md_final, "posture_mode": "unavailable", "error": "unavailable"})
        return
    except TimeoutError:
        yield ("error", {"code": "timeout", "provider": "litellm"})
        yield ("done", {**md_final, "error": "timeout"})
        return
    except Exception:  # noqa: BLE001
        logger.warning("litellm stream unexpected failure", exc_info=True)
        yield ("error", {"code": "unexpected", "provider": "litellm"})
        yield ("done", {**md_final, "error": "unexpected"})
        return

    yield ("done", md_final)


# ----------------------------------------------------------------------
# Top-level dispatch — picks the best available streaming backend, then
# falls back to a non-streaming chunked call if neither is reachable.
# Tier order mirrors ``services.ai_gateway.invoke`` for TaskType.
# ----------------------------------------------------------------------
def invoke_stream(
    task_type: Any,
    prompt: str,
    *,
    metadata: dict[str, Any] | None = None,
    user_query: str = "",
) -> Iterator[tuple[str, Any]]:
    """Stream the AI reply as ``("chunk", text)`` then ``("done", md)`` tuples.

    Honors the same posture/tier resolution that ``ai_gateway.invoke()`` uses,
    but only attempts streaming backends. If every streaming backend is
    unreachable, falls back to a single-shot ``invoke()`` and emits the full
    reply as one chunk before ``done``.
    """
    md_in = dict(metadata or {})

    # Resolve tier order via the existing posture module — the source of truth
    # for "what's available right now" is shared with the non-streaming path.
    try:
        from services.ai_gateway import _resolve_tier_order_for_task
        tiers = _resolve_tier_order_for_task(task_type, md_in)
    except Exception:  # noqa: BLE001
        tiers = ["ollama", "litellm"]

    streamers = {
        "ollama": stream_ollama,
        "litellm": stream_litellm,
    }

    for tier in tiers:
        streamer = streamers.get(tier)
        if not streamer:
            continue
        any_chunk = False
        last_done_md: dict[str, Any] | None = None
        had_error = False
        for kind, payload in streamer(prompt, md_in):
            if kind == "chunk":
                any_chunk = True
                yield ("chunk", payload)
            elif kind == "error":
                had_error = True
            elif kind == "done":
                last_done_md = payload if isinstance(payload, dict) else {}
        if any_chunk and not had_error and last_done_md is not None:
            yield ("done", last_done_md)
            return
        # Otherwise try the next tier.

    # Last-resort fallback: non-streaming invoke + single chunk emission.
    try:
        from services.ai_gateway import invoke as _invoke
        text, md = _invoke(task_type, prompt, user_query=user_query, metadata=md_in)
    except Exception:  # noqa: BLE001
        logger.warning("invoke_stream: fallback invoke crashed", exc_info=True)
        yield ("error", {"code": "fallback_failed"})
        yield ("done", {"posture_mode": "unavailable", "error": "fallback_failed"})
        return

    if text:
        yield ("chunk", text)
        yield ("done", md if isinstance(md, dict) else {"posture_mode": "guided"})
    else:
        yield ("done", {**(md if isinstance(md, dict) else {}), "posture_mode": "unavailable"})


__all__ = ("stream_ollama", "stream_litellm", "invoke_stream")
