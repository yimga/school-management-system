"""Tenant AI copilot rail — JSON endpoints (host-correct counterpart).

The shared rail template (``partials/cockpit/_ai_copilot_rail.html``) renders on
BOTH the manager control plane and tenant school workspaces, but its four
endpoints were hardcoded to the manager-only ``studio_os:`` routes. On a tenant
host those ``{% url %}`` reverses come back empty, the rail JS reads blank
endpoint URLs, no fetch fires, and every button is inert — the "copilot doesn't
work" report.

This module provides the TENANT counterparts. Critically they are tenant-scoped
and tenant-RBAC'd (``mode="tenant"`` / ``surface="tenant_copilot_rail"`` /
``task_type="general_chat"``), so a school admin never receives the operator /
fleet-flavored content the manager rail produces. Chat goes through the same
governed gateway as ``portal:ai_stream`` (PII redaction, availability gate,
audit), and works in rules-fallback mode (``require_available=False``) so it is
useful even when no LLM is configured.

The context/insights feeds are built from the school's live onboarding state, so
during first-run setup the rail proactively shows "you're 6% set up, next step
is …" — the crucial AI presence during onboarding.
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

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 4000  # magic-number-allow: tenant-copilot-rail-prompt-char-cap
_INSIGHTS_DEFAULT = 3
_INSIGHTS_HARD_MAX = 6  # magic-number-allow: tenant-copilot-rail-insights-hard-cap

_TENANT_MODE = "tenant"
_TENANT_SURFACE = "tenant_copilot_rail"
_TENANT_TASK_TYPE = "general_chat"


def _school(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is not None and getattr(school, "pk", None) is not None:
        return school
    # Freshly-provisioned schema-per-tenant: TenantSchemaSchoolBridgeMiddleware
    # leaves request.school None until the Client->School link is attached. With
    # no school the onboarding insight cards throw -> get swallowed -> the rail
    # feeds come back empty and the copilot "renders nothing". Fall back to the
    # canonical resolver (session / signup / SchoolMembership) — the same fix the
    # setup-wizard tile navigation uses (apps.setup_studio.wizard_views).
    try:
        from apps.lifecycle.tenant_school_resolve import resolve_request_school

        resolved = resolve_request_school(request)
        if resolved is not None and getattr(resolved, "pk", None) is not None:
            return resolved
    except Exception:  # noqa: BLE001 — resolution is best-effort; never break the rail
        logger.debug("copilot rail school resolve failed", exc_info=True)
    return school


def _insight_count(request: HttpRequest) -> int:
    raw = request.GET.get("n") or request.GET.get("count")
    if not raw:
        return _INSIGHTS_DEFAULT
    try:
        return max(1, min(int(raw), _INSIGHTS_HARD_MAX))
    except (TypeError, ValueError):
        return _INSIGHTS_DEFAULT


def _onboarding_insights(request: HttpRequest, n: int) -> list[dict]:
    try:
        from apps.platform_runtime.ai_onboarding_context import onboarding_insight_cards

        return onboarding_insight_cards(_school(request), limit=n)
    except Exception:  # noqa: BLE001 — insights are best-effort, never break the rail
        logger.debug("tenant copilot rail: onboarding insights failed", exc_info=True)
        return []


def _posture_mode() -> str:
    """Posture pill state the rail JS understands: live_cloud | guided.

    Cheap config check only (no network probe). With no cloud provider
    configured (the Render default) this is honestly "guided" (rules layer);
    chat still answers via the rules fallback.
    """
    try:
        from services.ai_deployment_posture import is_litellm_configured

        return "live_cloud" if is_litellm_configured() else "guided"
    except Exception:  # noqa: BLE001 — posture is cosmetic; default to guided
        return "guided"


def _tenant_quick_actions(request: HttpRequest) -> list[dict]:
    """Up to a couple of always-useful tenant actions for the rail (registry shape)."""
    from django.urls import reverse

    actions: list[dict] = []
    try:
        actions.append({
            "label": "Open setup wizards",
            "url": reverse("setup_studio:tenant_wizard_index"),
            "icon": "✨",
            "kind": "setup",
        })
    except Exception:  # noqa: BLE001 — action list is best-effort
        pass
    return actions


@method_decorator(never_cache, name="dispatch")
class TenantCopilotRailContextView(LoginRequiredMixin, View):
    """Full rail bootstrap payload, tenant-scoped (onboarding-driven insights)."""

    http_method_names = ["get"]
    raise_exception = False

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        n = _insight_count(request)
        posture = _posture_mode()
        return JsonResponse({
            "snapshot": {"posture_mode": posture, "mode": "school"},
            "insights": _onboarding_insights(request, n),
            "quick_actions": _tenant_quick_actions(request),
            "posture_mode": posture,
        })


@method_decorator(never_cache, name="dispatch")
class TenantCopilotRailInsightsView(LoginRequiredMixin, View):
    """Just the insights array — the rail's periodic refresh cycle."""

    http_method_names = ["get"]
    raise_exception = False

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        n = _insight_count(request)
        return JsonResponse({
            "insights": _onboarding_insights(request, n),
            "posture_mode": _posture_mode(),
        })


def _read_message(request: HttpRequest) -> tuple[str, str | None]:
    """Return (message, error_code). error_code is None on success."""
    try:
        body = (request.body or b"").decode("utf-8", errors="replace")
        data = json.loads(body) if body else {}
    except (ValueError, json.JSONDecodeError):
        return "", "bad_json"
    message = ""
    if isinstance(data, dict):
        message = str(data.get("message") or "").strip()
    if not message:
        return "", "empty_message"
    if len(message) > _MAX_PROMPT_CHARS:
        return "", "message_too_long"
    return message, None


def _prepare_tenant_invoke(request: HttpRequest, message: str, *, surface: str):
    """RBAC-gated tenant copilot envelope, grounded in onboarding state."""
    from services.ai_copilot_rbac import prepare_copilot_invoke

    envelope = prepare_copilot_invoke(
        request,
        message,
        mode=_TENANT_MODE,
        surface=surface,
        task_type=_TENANT_TASK_TYPE,
    )
    # Inject onboarding grounding so rules-mode answers are useful during setup.
    if getattr(envelope, "allowed", False):
        try:
            from apps.platform_runtime.ai_onboarding_context import (
                build_onboarding_context_for_ai,
                onboarding_prompt_preamble,
            )

            school = _school(request)
            if isinstance(getattr(envelope, "metadata", None), dict):
                envelope.metadata.update(build_onboarding_context_for_ai(school))
            preamble = onboarding_prompt_preamble(school)
            if preamble and getattr(envelope, "prompt", None):
                envelope.prompt = preamble + "\n\n" + envelope.prompt
        except Exception:  # noqa: BLE001 — grounding is additive, never blocks chat
            logger.debug("tenant copilot rail: onboarding grounding failed", exc_info=True)
    return envelope


def _source_from_metadata(md) -> str:
    if not isinstance(md, dict):
        return "rules"
    provider = (md.get("provider") or "").lower()
    posture = md.get("posture_mode") or ""
    if "ollama" in provider or posture == "live_local":
        return "local"
    if posture in {"unavailable", "off"}:
        return "unavailable"
    if posture == "guided" or provider in {"none", "rules"} or md.get("tier") == "rules":
        return "rules"
    return "cloud"


def _reply_text(ai_result) -> str:
    try:
        from services.ai_copilot_reply_format import extract_copilot_rail_reply

        text = extract_copilot_rail_reply(ai_result)
    except Exception:  # noqa: BLE001 — fall back to a stringified result
        text = ai_result if isinstance(ai_result, str) else ""
    return text or "I didn't have a useful reply for that. Try asking about a specific setup step."


@method_decorator(never_cache, name="dispatch")
class TenantCopilotRailSendView(LoginRequiredMixin, View):
    """Tenant chat — POST a message, return a single AI reply (rules-mode safe)."""

    http_method_names = ["post"]
    raise_exception = False

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        message, err = _read_message(request)
        if err:
            status = 400
            return JsonResponse({"reply": "", "source": "unavailable", "error": err}, status=status)

        envelope = _prepare_tenant_invoke(request, message, surface=_TENANT_SURFACE)
        if not envelope.allowed:
            return JsonResponse({
                "reply": envelope.denial_reason,
                "source": "unavailable",
                "error": "permission_denied",
                "posture_mode": "unavailable",
            }, status=403)

        try:
            from services.ai_helpers import invoke_with_request
        except ImportError:
            logger.warning("tenant copilot rail send: ai_helpers import failed", exc_info=True)
            return JsonResponse({
                "reply": "The assistant isn't configured for this environment yet.",
                "source": "unavailable",
                "posture_mode": "unavailable",
            })

        try:
            result = invoke_with_request(
                task_type=_TENANT_TASK_TYPE,
                prompt=envelope.prompt,
                request=request,
                user_query=message,
                metadata=envelope.metadata,
                response_schema="guided_assistant",
                require_available=False,
            )
        except Exception:  # noqa: BLE001 — chat must degrade, never 500
            logger.warning("tenant copilot rail send: invoke failed", exc_info=True)
            return JsonResponse({
                "reply": "Sorry — the assistant had trouble responding. Please try again.",
                "source": "unavailable",
                "posture_mode": "unavailable",
            })

        if result is None:
            return JsonResponse({
                "reply": "The assistant is unavailable right now. The setup wizards in the sidebar walk you through every step.",
                "source": "unavailable",
                "posture_mode": "unavailable",
            })

        try:
            ai_result, md = result
        except (TypeError, ValueError):
            ai_result, md = result, {}

        source = _source_from_metadata(md)
        return JsonResponse({
            "reply": _reply_text(ai_result),
            "source": source,
            "posture_mode": (md.get("posture_mode") if isinstance(md, dict) else "") or source,
            "request_id": (md.get("request_id") if isinstance(md, dict) else "") or "",
        })


def _sse(event: str, payload: dict) -> bytes:
    return ("event: " + event + "\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


_STREAM_CHUNK_CHARS = 60  # magic-number-allow: tenant-copilot-stream-chunk-size
_STREAM_SLEEP = 0.03


def _chunk(text: str, size: int = _STREAM_CHUNK_CHARS):
    pos, n = 0, len(text or "")
    while pos < n:
        end = min(pos + size, n)
        if end < n:
            space = text.rfind(" ", max(end - 12, pos + 1), end)
            if space != -1:
                end = space + 1
        yield text[pos:end]
        pos = end


@method_decorator(never_cache, name="dispatch")
class TenantCopilotRailSendStreamView(LoginRequiredMixin, View):
    """Tenant chat with progressive SSE chunks (single-shot invoke + chunker)."""

    http_method_names = ["post"]
    raise_exception = False

    def post(self, request: HttpRequest, *args, **kwargs) -> StreamingHttpResponse:
        message, err = _read_message(request)
        if err:
            return self._error_stream(err)

        envelope = _prepare_tenant_invoke(request, message, surface=_TENANT_SURFACE + "_stream")
        if not envelope.allowed:
            return self._error_stream("permission_denied", status=403, reply=envelope.denial_reason)

        def stream():
            yield _sse("ready", {"posture_mode": "pending", "request_id": ""})
            try:
                from services.ai_helpers import invoke_with_request
            except ImportError:
                yield _sse("done", {"reply": "The assistant isn't configured here yet.", "source": "unavailable", "posture_mode": "unavailable", "request_id": ""})
                return
            try:
                result = invoke_with_request(
                    task_type=_TENANT_TASK_TYPE,
                    prompt=envelope.prompt,
                    request=request,
                    user_query=message,
                    metadata=envelope.metadata,
                    response_schema="guided_assistant",
                    require_available=False,
                )
            except Exception:  # noqa: BLE001 — stream must close cleanly
                logger.warning("tenant copilot rail stream: invoke failed", exc_info=True)
                yield _sse("error", {"code": "invoke_failed"})
                yield _sse("done", {"reply": "Sorry — the assistant had trouble responding.", "source": "unavailable", "posture_mode": "unavailable", "request_id": ""})
                return
            if result is None:
                yield _sse("done", {"reply": "The assistant is unavailable right now. Use the setup wizards in the sidebar.", "source": "unavailable", "posture_mode": "unavailable", "request_id": ""})
                return
            try:
                ai_result, md = result
            except (TypeError, ValueError):
                ai_result, md = result, {}
            reply = _reply_text(ai_result)
            source = _source_from_metadata(md)
            for piece in _chunk(reply):
                yield _sse("delta", {"text": piece})
                if _STREAM_SLEEP > 0:
                    time.sleep(_STREAM_SLEEP)
            yield _sse("done", {
                "reply": reply,
                "source": source,
                "posture_mode": (md.get("posture_mode") if isinstance(md, dict) else "") or source,
                "request_id": (md.get("request_id") if isinstance(md, dict) else "") or "",
            })

        response = StreamingHttpResponse(stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        return response

    @staticmethod
    def _error_stream(code: str, *, status: int = 400, reply: str = "") -> StreamingHttpResponse:
        def _gen():
            yield _sse("error", {"code": code})
            yield _sse("done", {"reply": reply, "source": "unavailable", "posture_mode": "unavailable", "request_id": ""})

        response = StreamingHttpResponse(_gen(), content_type="text/event-stream", status=status)
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        return response


__all__ = (
    "TenantCopilotRailContextView",
    "TenantCopilotRailInsightsView",
    "TenantCopilotRailSendView",
    "TenantCopilotRailSendStreamView",
)
