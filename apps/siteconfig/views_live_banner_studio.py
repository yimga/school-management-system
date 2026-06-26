"""Live Banner Studio AI assist endpoints (rules-first, optional gateway enrich)."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)


def _forbidden(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"ok": False, "error": "forbidden"}, status=403)


def _may_configure_live_banner(request: HttpRequest) -> bool:
    from apps.siteconfig.tenant_experience_policy import user_may_configure_tenant_experience

    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user_may_configure_tenant_experience(user))


@login_required
@require_GET
def api_live_banner_suggest_program(request: HttpRequest) -> JsonResponse:
    if not _may_configure_live_banner(request):
        return _forbidden(request)

    from apps.siteconfig.cockpit_live_banner_program import (
        suggest_live_banner_program,
        validate_live_banner_program_payload,
    )

    program = suggest_live_banner_program(request)
    errors = validate_live_banner_program_payload(program)
    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    source = "rules"
    if getattr(settings, "AI_GATEWAY_ENABLED", True):
        try:
            from services.ai_copilot_rbac import guard_copilot_invoke
            from services.ai_helpers import invoke_with_request

            prompt = (
                "Return ONLY compact JSON with keys sources_enabled (manager/tenant string lists), "
                "announcements (array of {kind,text,severity,pin,audiences}), scroll_seconds, live_badge_label. "
                "No markdown. Operator live banner for school SaaS."
            )
            guard = guard_copilot_invoke(
                request=request,
                task_type="setup_recommend",
                prompt=prompt,
                user_query="",
                metadata={"surface": "live_banner_studio_suggest"},
            )
            result = invoke_with_request(
                task_type="setup_recommend",
                prompt=guard.prompt,
                request=request,
                metadata=guard.metadata,
                require_available=False,
            )
            if result is not None:
                text, _meta = result
                if text and isinstance(text, str):
                    candidate = json.loads(text.strip())
                    if isinstance(candidate, dict):
                        candidate_errors = validate_live_banner_program_payload(candidate)
                        if not candidate_errors:
                            program = candidate
                            source = "ai"
        except Exception as exc:  # noqa: BLE001
            logger.debug("live_banner suggest optional AI failed: %s", exc)

    return JsonResponse({"ok": True, "program": program, "source": source})


@login_required
@require_POST
def api_live_banner_draft_emergency(request: HttpRequest) -> JsonResponse:
    if not _may_configure_live_banner(request):
        return _forbidden(request)

    from apps.siteconfig.cockpit_live_banner_program import draft_emergency_announcement

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}
    topic = str(body.get("topic") or request.POST.get("topic") or "").strip()
    announcement = draft_emergency_announcement(request, topic=topic)

    if getattr(settings, "AI_GATEWAY_ENABLED", True) and topic:
        try:
            from services.ai_copilot_rbac import guard_copilot_invoke
            from services.ai_helpers import invoke_with_request

            prompt = (
                "Draft one emergency school announcement sentence. Plain text only. "
                f"Topic: {topic[:200]}. No PII."
            )
            guard = guard_copilot_invoke(
                request=request,
                task_type="setup_recommend",
                prompt=prompt,
                user_query=topic[:200],
                metadata={"surface": "live_banner_studio_emergency"},
            )
            result = invoke_with_request(
                task_type="setup_recommend",
                prompt=guard.prompt,
                request=request,
                metadata=guard.metadata,
                require_available=False,
            )
            if result is not None:
                text, _meta = result
                if text and isinstance(text, str) and len(text.strip()) > 12:
                    announcement["text"] = text.strip()[:280]
        except Exception as exc:  # noqa: BLE001
            logger.debug("live_banner emergency optional AI failed: %s", exc)

    return JsonResponse({"ok": True, "announcement": announcement})
