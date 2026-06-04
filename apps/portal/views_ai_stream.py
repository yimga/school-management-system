"""Streaming AI gateway view (v4.00.9).

Pipes ``services.ai_gateway_stream.stream_litellm`` chunks into a
``StreamingHttpResponse`` so the client-side ``rmcStreamMount.attachFetch``
parser can mount UI fragments progressively.

Endpoint: ``POST /portal/ai/stream/``
Body: ``{"prompt": "<text>"}``
Headers: ``X-RMC-Viewport: A|B|C`` (optional; defaults to A)

The response is a server-sent-event style stream of ``data: <chunk>`` lines
terminated with ``data: [DONE]`` so the same client parser handles edge
proxy + Django origin uniformly.

When LiteLLM is not configured the view returns 503; the client falls back
to the legacy non-streaming path.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_MAX_PROMPT_BYTES = 32 * 1024  # 32 KiB cap; mobile shaping strips most


def _resolve_viewport(request: HttpRequest) -> str:
    return (request.META.get("HTTP_X_RMC_VIEWPORT", "") or "A").strip().upper()[:1] or "A"


def _sse_pack(chunk: str) -> bytes:
    # SSE rule: each "data:" line; events separated by blank line.
    safe = chunk.replace("\r\n", "\n").replace("\r", "\n")
    payload = "\n".join(f"data: {line}" for line in safe.split("\n")) + "\n\n"
    return payload.encode("utf-8")


def _stream_chunks(request: HttpRequest, prompt: str, viewport: str) -> Iterator[bytes]:
    """Bridge the GOVERNED streaming gateway -> SSE bytes.

    v4.01 SECURITY — routes through ``services.ai_helpers.invoke_with_request_stream``
    instead of the raw ``ai_gateway_stream.stream_litellm``. The raw path piped
    the user prompt straight to cloud LiteLLM with NO PII redaction, NO
    prompt-injection block, NO data-tier/availability gate, and NO audit — a
    complete end-run around the gateway contract. The helper applies the SAME
    protections as the non-streaming gateway (PII redaction, AI-availability /
    data-tier policy, tenant metadata, injection block + audit inside
    ``invoke_stream``). Always yields a ``[DONE]`` terminator.
    """
    try:
        from services.ai_helpers import invoke_with_request_stream
    except ImportError:
        yield _sse_pack("[ERROR] streaming gateway unavailable")
        yield b"data: [DONE]\n\n"
        return
    gen = invoke_with_request_stream(
        task_type="general_chat",
        prompt=prompt,
        request=request,
        metadata={"viewport": viewport, "surface": "portal_ai_stream"},
        require_available=False,
    )
    if gen is None:
        yield _sse_pack("[ERROR] ai_unavailable")
        yield b"data: [DONE]\n\n"
        return
    try:
        for kind, payload in gen:
            if kind == "chunk" and payload:
                yield _sse_pack(payload if isinstance(payload, str) else str(payload))
            elif kind == "error":
                code = payload.get("code") if isinstance(payload, dict) else payload
                yield _sse_pack(f"[ERROR] {code}")
    except Exception as exc:  # noqa: BLE001 — streaming must always close cleanly
        logger.warning("ai_stream.yield_failed: %s", exc)
    yield b"data: [DONE]\n\n"


@csrf_protect
@login_required
@require_http_methods(["POST"])
def ai_stream_view(request: HttpRequest) -> Any:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return JsonResponse({"ok": False, "error": "no_prompt"}, status=400)
    if len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
        return JsonResponse({"ok": False, "error": "prompt_too_large"}, status=413)
    try:
        from services.ai_deployment_posture import is_litellm_configured
    except ImportError:
        return JsonResponse({"ok": False, "error": "gateway_unconfigured"}, status=503)
    if not is_litellm_configured():
        return JsonResponse({"ok": False, "error": "litellm_unconfigured"}, status=503)
    host_kind = (getattr(request, "public_host_kind", None) or "").lower()
    if host_kind == "tenant" and getattr(request, "school", None) is None:
        return JsonResponse({"ok": False, "error": "tenant_required"}, status=403)
    viewport = _resolve_viewport(request)
    response = StreamingHttpResponse(
        _stream_chunks(request, prompt, viewport),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disable nginx buffering for SSE
    response["X-RMC-Viewport"] = viewport
    return response
