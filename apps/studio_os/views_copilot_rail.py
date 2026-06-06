"""Studio OS Co-pilot Rail — JSON endpoints (v3.58.5, 2026-05-22).

Four endpoints back the persistent AI presence panel:

  * GET  /studio/copilot/rail/context/      — full snapshot + insights + quick_actions
  * GET  /studio/copilot/rail/insights/     — just the insights refresh payload (90s cycle)
  * POST /studio/copilot/rail/send/         — operator-typed chat message (single JSON)
  * POST /studio/copilot/rail/send-stream/  — operator chat with progressive SSE chunks

All are login-gated via ``LoginRequiredMixin``. Tenant scoping is inherited
from the request — the service module never accesses a foreign school. PII
isn't logged; only the sha256[:8] of the slug ever lands on a log line.

Streaming posture (v3.58.5):
  The streaming endpoint invokes ``ai_helpers.invoke_with_request`` once
  (the gateway returns the full reply — true token-by-token streaming
  requires backend-level stream support per-provider, deferred). Then it
  yields the reply in ~60-char SSE frames with a 30ms gap so the operator
  sees progressive ink rather than a jarring full-text flash. When the
  gateway gains a real streaming API, the inner loop is the only thing
  that changes — the wire protocol stays SSE.
"""

from __future__ import annotations

import json
import logging
import time

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from .copilot_rail_service import (
    build_context_snapshot,
    build_rail_payload,
    generate_insights,
)

logger = logging.getLogger(__name__)

# Hard upper bound — the front-end UI only renders 3 insights; we cap to 6 so
# malicious or buggy callers can't ask for a 1000-row prompt.
_INSIGHTS_HARD_MAX = 6
_INSIGHTS_DEFAULT = 3


def _resolve_mode(request: HttpRequest) -> str:
    """Read the active studio mode from query string or referrer hint."""
    mode = (request.GET.get("mode") or "").strip().lower()
    if mode:
        return mode[:24]
    # Fall back to nothing — the service maps unknown surfaces to 'shell'.
    return ""


def _resolve_count(request: HttpRequest, *, default: int) -> int:
    raw = request.GET.get("n") or request.GET.get("count")
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, _INSIGHTS_HARD_MAX))


@method_decorator(never_cache, name="dispatch")
class CopilotRailContextView(LoginRequiredMixin, View):
    """Returns the full rail bootstrap payload for the operator's context."""

    http_method_names = ["get"]
    raise_exception = False

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        mode = _resolve_mode(request)
        n = _resolve_count(request, default=_INSIGHTS_DEFAULT)
        try:
            payload = build_rail_payload(request, mode=mode, n=n)
        except Exception:  # noqa: BLE001
            logger.warning(
                "copilot_rail_context: build_rail_payload failed",
                exc_info=True,
            )
            return JsonResponse(
                {
                    "snapshot": None,
                    "insights": [],
                    "quick_actions": [],
                    "error": "unavailable",
                },
                status=200,
            )
        return JsonResponse(payload)


@method_decorator(never_cache, name="dispatch")
class CopilotRailInsightsRefreshView(LoginRequiredMixin, View):
    """Returns just the insights array — called on the 90s refresh cycle."""

    http_method_names = ["get"]
    raise_exception = False

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        mode = _resolve_mode(request)
        n = _resolve_count(request, default=_INSIGHTS_DEFAULT)
        try:
            snapshot = build_context_snapshot(request, mode=mode)
            insights = generate_insights(snapshot, request=request, n=n)
        except Exception:  # noqa: BLE001
            logger.warning(
                "copilot_rail_insights: refresh failed",
                exc_info=True,
            )
            return JsonResponse({"insights": []}, status=200)
        return JsonResponse(
            {
                "insights": [i.to_dict() for i in insights],
                "posture_mode": snapshot.posture_mode,
            }
        )


# Hard upper bound on operator-typed message length. Anything beyond this is
# almost certainly a paste of structured content (logs, JSON) — kindly refuse
# so the gateway prompt budget isn't blown on accidents.
_MAX_PROMPT_CHARS = 4000


def _prepare_rail_invoke(request: HttpRequest, message: str, *, mode: str, surface: str):
    from services.ai_copilot_rbac import prepare_copilot_invoke

    return prepare_copilot_invoke(
        request,
        message,
        mode=mode,
        surface=surface,
        task_type="studio_os_assistant",
    )


@method_decorator(never_cache, name="dispatch")
class CopilotRailSendView(LoginRequiredMixin, View):
    """Operator chat — POSTs a message, returns a single AI reply.

    Wraps ``services.ai_helpers.invoke_with_request`` so the rail surface
    goes through the canonical gateway (LiteLLM cloud / local Ollama /
    rules-layer fallback) per the platform's AI deployment posture.

    Request body (JSON):
        {"message": "...", "mode": "operator"}

    Response (JSON, always 200 — failures degrade gracefully):
        {"reply": "...", "source": "cloud|local|rules|unavailable",
         "posture_mode": "...", "request_id": "..."}
    """

    http_method_names = ["post"]
    raise_exception = False

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        message = ""
        try:
            body = (request.body or b"").decode("utf-8", errors="replace")
            if body:
                data = json.loads(body)
                if isinstance(data, dict):
                    message = str(data.get("message") or "").strip()
        except (ValueError, json.JSONDecodeError):
            return JsonResponse(
                {"reply": "", "source": "unavailable", "error": "bad_json"},
                status=400,
            )
        if not message:
            return JsonResponse(
                {"reply": "", "source": "unavailable", "error": "empty_message"},
                status=400,
            )
        if len(message) > _MAX_PROMPT_CHARS:
            return JsonResponse(
                {
                    "reply": "",
                    "source": "unavailable",
                    "error": "message_too_long",
                    "max_chars": _MAX_PROMPT_CHARS,
                },
                status=400,
            )

        mode = _resolve_mode(request) or "operator"
        envelope = _prepare_rail_invoke(
            request,
            message,
            mode=mode,
            surface="studio_os_copilot_rail",
        )
        if not envelope.allowed:
            return JsonResponse(
                {
                    "reply": envelope.denial_reason,
                    "source": "unavailable",
                    "error": "permission_denied",
                    "posture_mode": "unavailable",
                },
                status=403,
            )

        try:
            from services.ai_helpers import TaskType, invoke_with_request
        except ImportError:
            logger.warning("copilot_rail_send: ai_helpers import failed", exc_info=True)
            return JsonResponse({
                "reply": "AI gateway is not configured for this environment.",
                "source": "unavailable",
                "posture_mode": "unavailable",
            })

        try:
            result = invoke_with_request(
                task_type=TaskType.STUDIO_OS_ASSISTANT,
                prompt=envelope.prompt,
                request=request,
                user_query=message,
                metadata=envelope.metadata,
                require_available=False,
            )
        except Exception:  # noqa: BLE001
            logger.warning("copilot_rail_send: invoke failed", exc_info=True)
            return JsonResponse({
                "reply": "Sorry — the assistant had trouble responding. Please try again.",
                "source": "unavailable",
                "posture_mode": "unavailable",
            })

        # invoke_with_request returns either (result, metadata) or None.
        if result is None:
            return JsonResponse({
                "reply": "AI is unavailable right now. Try the command palette (⌘K) for quick actions.",
                "source": "unavailable",
                "posture_mode": "unavailable",
            })

        try:
            ai_result, md = result
        except (TypeError, ValueError):
            ai_result, md = result, {}

        reply_text = ""
        if hasattr(ai_result, "text") and isinstance(ai_result.text, str):
            reply_text = ai_result.text
        elif isinstance(ai_result, dict):
            reply_text = str(ai_result.get("text") or ai_result.get("reply") or "")
        elif isinstance(ai_result, str):
            reply_text = ai_result
        if not reply_text:
            reply_text = "I didn't have a useful reply for that. Try rephrasing or ask about a specific tenant."

        source = "cloud"
        if isinstance(md, dict):
            provider = (md.get("provider") or "").lower()
            if "ollama" in provider or md.get("posture_mode") == "live_local":
                source = "local"
            elif md.get("posture_mode") == "guided" or provider == "none":
                source = "rules"
            elif md.get("posture_mode") in {"unavailable", "off"}:
                source = "unavailable"

        return JsonResponse({
            "reply": reply_text,
            "source": source,
            "posture_mode": (md.get("posture_mode") if isinstance(md, dict) else "") or source,
            "request_id": (md.get("request_id") if isinstance(md, dict) else "") or "",
        })


# ----------------------------------------------------------------------
# v3.58.5 — Streaming chat replies (SSE).
# ----------------------------------------------------------------------

# Wire tuning. Conservative defaults so the UX feels responsive on cold
# replies without flooding the wire. Operators can tune via env / settings
# if a future deployment finds these need adjusting.
_STREAM_CHUNK_CHARS = 60
_STREAM_INTER_CHUNK_SLEEP_SECS = 0.03
_STREAM_HARD_TIMEOUT_SECS = 90.0


def _sse(event: str, payload: dict) -> bytes:
    """Format one SSE frame as wire bytes."""
    body = "event: " + event + "\n"
    body += "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
    return body.encode("utf-8")


def _chunk_text(text: str, size: int = _STREAM_CHUNK_CHARS):
    """Yield ``text`` in slices of up to ``size`` chars, preferring word breaks."""
    if not text:
        return
    pos = 0
    n = len(text)
    while pos < n:
        end = min(pos + size, n)
        # Prefer to break on a space within the last 12 chars of the slice
        # so words don't get sawed in half mid-render. Cheap heuristic; falls
        # back to hard slice when no space is found.
        if end < n:
            window_start = max(end - 12, pos + 1)
            space_at = text.rfind(" ", window_start, end)
            if space_at != -1:
                end = space_at + 1
        yield text[pos:end]
        pos = end


def _derive_source(md: dict) -> str:
    """Mirror the source-pill mapping used by CopilotRailSendView."""
    if not isinstance(md, dict):
        return "cloud"
    provider = (md.get("provider") or "").lower()
    posture = md.get("posture_mode") or ""
    if "ollama" in provider or posture == "live_local":
        return "local"
    if posture == "guided" or provider == "none":
        return "rules"
    if posture in {"unavailable", "off"}:
        return "unavailable"
    return "cloud"


@method_decorator(never_cache, name="dispatch")
class CopilotRailSendStreamView(LoginRequiredMixin, View):
    """Operator chat — POSTs a message, returns SSE-framed progressive reply.

    Wire protocol::

        event: ready
        data: {"posture_mode": "live_cloud", "request_id": "..."}

        event: delta
        data: {"text": "first chunk of the reply"}

        event: delta
        data: {"text": "second chunk..."}

        event: done
        data: {"reply": "<full reply>", "source": "cloud",
               "posture_mode": "live_cloud", "request_id": "..."}

    Errors degrade to a single ``event: error`` frame followed by ``event: done``
    with ``source=unavailable`` so the client can always close cleanly.
    """

    http_method_names = ["post"]
    raise_exception = False

    def post(self, request: HttpRequest, *args, **kwargs) -> StreamingHttpResponse:
        message = ""
        try:
            body = (request.body or b"").decode("utf-8", errors="replace")
            if body:
                data = json.loads(body)
                if isinstance(data, dict):
                    message = str(data.get("message") or "").strip()
        except (ValueError, json.JSONDecodeError):
            return self._error_stream("bad_json", status=400)
        if not message:
            return self._error_stream("empty_message", status=400)
        if len(message) > _MAX_PROMPT_CHARS:
            return self._error_stream("message_too_long", status=400, extra={"max_chars": _MAX_PROMPT_CHARS})

        mode = _resolve_mode(request) or "operator"
        envelope = _prepare_rail_invoke(
            request,
            message,
            mode=mode,
            surface="studio_os_copilot_rail_stream",
        )
        if not envelope.allowed:
            return self._permission_denied_stream(envelope.denial_reason)

        def stream():
            t_start = time.monotonic()
            # Prefer true token-by-token streaming via the ai_helpers stream
            # wrapper (v3.59.2). On any import / setup failure fall back to the
            # single-shot invoke + server-side chunker so the SSE wire shape
            # stays consistent for the JS consumer.
            try:
                from services.ai_helpers import (
                    TaskType,
                    invoke_with_request,
                    invoke_with_request_stream,
                )
            except ImportError:
                logger.warning("copilot_rail_send_stream: ai_helpers import failed", exc_info=True)
                yield _sse("error", {"code": "gateway_unavailable"})
                yield _sse("done", {
                    "reply": "AI gateway is not configured for this environment.",
                    "source": "unavailable",
                    "posture_mode": "unavailable",
                    "request_id": "",
                })
                return

            yield _sse("ready", {"posture_mode": "pending", "request_id": ""})

            stream_md = dict(envelope.metadata)
            stream_md["surface"] = "studio_os_copilot_rail_stream"
            stream_md["mode"] = mode
            rail_prompt = envelope.prompt

            # ---- Attempt true streaming first ----
            assembled_parts: list[str] = []
            final_md: dict = {}
            stream_yielded_any = False
            stream_had_error = False
            try:
                gen = invoke_with_request_stream(
                    task_type=TaskType.STUDIO_OS_ASSISTANT,
                    prompt=rail_prompt,
                    request=request,
                    user_query=message,
                    metadata=stream_md,
                    require_available=False,
                )
            except Exception:  # noqa: BLE001
                logger.warning("copilot_rail_send_stream: stream setup failed", exc_info=True)
                gen = None

            if gen is not None:
                try:
                    for kind, payload in gen:
                        if time.monotonic() - t_start > _STREAM_HARD_TIMEOUT_SECS:
                            break
                        if kind == "chunk" and isinstance(payload, str) and payload:
                            stream_yielded_any = True
                            assembled_parts.append(payload)
                            yield _sse("delta", {"text": payload})
                        elif kind == "error":
                            stream_had_error = True
                        elif kind == "done":
                            if isinstance(payload, dict):
                                final_md = payload
                except Exception:  # noqa: BLE001
                    logger.warning("copilot_rail_send_stream: stream iteration failed", exc_info=True)
                    stream_had_error = True

            # If streaming worked, finalize and exit.
            if stream_yielded_any and not stream_had_error:
                reply_text = "".join(assembled_parts) or "I didn't have a useful reply for that."
                source = _derive_source(final_md)
                posture_mode = str(final_md.get("posture_mode") or "") or source
                request_id = str(final_md.get("request_id") or "")
                yield _sse("done", {
                    "reply": reply_text,
                    "source": source,
                    "posture_mode": posture_mode,
                    "request_id": request_id,
                })
                return

            # ---- Fallback: single-shot invoke + server-side chunker ----
            try:
                result = invoke_with_request(
                    task_type=TaskType.STUDIO_OS_ASSISTANT,
                    prompt=rail_prompt,
                    request=request,
                    user_query=message,
                    metadata={**stream_md, "surface": "studio_os_copilot_rail_stream_fallback"},
                    require_available=False,
                )
            except Exception:  # noqa: BLE001
                logger.warning("copilot_rail_send_stream: invoke failed", exc_info=True)
                yield _sse("error", {"code": "invoke_failed"})
                yield _sse("done", {
                    "reply": "Sorry — the assistant had trouble responding. Please try again.",
                    "source": "unavailable",
                    "posture_mode": "unavailable",
                    "request_id": "",
                })
                return

            if result is None:
                yield _sse("done", {
                    "reply": "AI is unavailable right now. Try the command palette (⌘K) for quick actions.",
                    "source": "unavailable",
                    "posture_mode": "unavailable",
                    "request_id": "",
                })
                return

            try:
                ai_result, md = result
            except (TypeError, ValueError):
                ai_result, md = result, {}

            reply_text = ""
            if hasattr(ai_result, "text") and isinstance(ai_result.text, str):
                reply_text = ai_result.text
            elif isinstance(ai_result, dict):
                reply_text = str(ai_result.get("text") or ai_result.get("reply") or "")
            elif isinstance(ai_result, str):
                reply_text = ai_result
            if not reply_text:
                reply_text = "I didn't have a useful reply for that. Try rephrasing or ask about a specific tenant."

            source = _derive_source(md if isinstance(md, dict) else {})
            posture_mode = ""
            request_id = ""
            if isinstance(md, dict):
                posture_mode = str(md.get("posture_mode") or "") or source
                request_id = str(md.get("request_id") or "")
            else:
                posture_mode = source

            for chunk in _chunk_text(reply_text):
                if time.monotonic() - t_start > _STREAM_HARD_TIMEOUT_SECS:
                    break
                yield _sse("delta", {"text": chunk})
                if _STREAM_INTER_CHUNK_SLEEP_SECS > 0:
                    time.sleep(_STREAM_INTER_CHUNK_SLEEP_SECS)

            yield _sse("done", {
                "reply": reply_text,
                "source": source,
                "posture_mode": posture_mode,
                "request_id": request_id,
            })

        response = StreamingHttpResponse(stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"  # nginx: disable response buffering
        return response

    @staticmethod
    def _permission_denied_stream(message: str) -> StreamingHttpResponse:
        def _gen():
            yield _sse("error", {"code": "permission_denied"})
            yield _sse("done", {
                "reply": message,
                "source": "unavailable",
                "posture_mode": "unavailable",
                "request_id": "",
            })

        response = StreamingHttpResponse(_gen(), content_type="text/event-stream", status=403)
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        return response

    @staticmethod
    def _error_stream(code: str, *, status: int = 400, extra: dict | None = None) -> StreamingHttpResponse:
        payload = {"code": code}
        if extra:
            payload.update(extra)

        def _gen():
            yield _sse("error", payload)
            yield _sse("done", {
                "reply": "",
                "source": "unavailable",
                "posture_mode": "unavailable",
                "request_id": "",
            })

        response = StreamingHttpResponse(_gen(), content_type="text/event-stream", status=status)
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        return response


__all__ = (
    "CopilotRailContextView",
    "CopilotRailInsightsRefreshView",
    "CopilotRailSendView",
    "CopilotRailSendStreamView",
)
