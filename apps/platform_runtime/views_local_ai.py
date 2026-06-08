"""Authenticated tenant endpoints for optional local browser and voice AI."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.compliance.models_audit import AuditLog
from apps.platform_runtime.browser_inference import browser_inference_public_config
from services.http_auth_guards import login_required_api
from services.local_voice import LocalVoiceError, synthesize, transcribe

logger = logging.getLogger(__name__)


def _tenant_required(request):
    school = getattr(request, "school", None)
    if school is None:
        return None, JsonResponse({"error": "tenant_required"}, status=403)
    return school, None


def _consent(request, body=None) -> bool:
    header = str(request.headers.get("X-RMC-Voice-Consent", "")).lower()
    return header in {"1", "true", "yes"} or bool((body or {}).get("consent"))


def _voice_rate_limit(request, school):
    limit = max(1, int(getattr(settings, "LOCAL_VOICE_RATE_LIMIT_PER_MINUTE", 10)))
    bucket = int(timezone.now().timestamp() // 60)
    key = (
        f"local_voice:{getattr(school, 'pk', '')}:"
        f"{getattr(request.user, 'pk', '')}:{bucket}"
    )
    try:
        if cache.add(key, 1, timeout=70):
            return None
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=70)
            count = 1
    except Exception:
        logger.warning("local_voice_rate_limit_unavailable", exc_info=True)
        return JsonResponse({"error": "voice_guard_unavailable"}, status=503)
    if count <= limit:
        return None
    response = JsonResponse({"error": "rate_limited"}, status=429)
    response["Retry-After"] = "60"
    return response


def _audit_voice(request, school, action: str, language: str, byte_count: int):
    try:
        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.VIEW,
            model_name="LocalVoiceAccessibility",
            object_id=str(getattr(school, "pk", "")),
            object_repr=action,
            app_label="platform_runtime",
            sensitivity=AuditLog.Sensitivity.MEDIUM,
            new_values={
                "operation": action,
                "language": language,
                "byte_count": byte_count,
                "content_retained": False,
            },
            reason="Explicit-consent local voice accessibility request",
        )
    except Exception:
        logger.warning("local_voice_audit_failed", exc_info=True)


@require_GET
@login_required_api
def browser_inference_config_view(request):
    _school, error = _tenant_required(request)
    if error:
        return error
    return JsonResponse(browser_inference_public_config())


@require_POST
@login_required_api
def local_voice_transcribe_view(request):
    school, error = _tenant_required(request)
    if error:
        return error
    if not _consent(request):
        return JsonResponse({"error": "explicit_consent_required"}, status=400)
    limited = _voice_rate_limit(request, school)
    if limited:
        return limited
    language = request.headers.get("X-RMC-Voice-Language", "en")
    content_type = (request.content_type or "application/octet-stream").split(";")[0]
    try:
        text = transcribe(
            bytes(request.body), content_type=content_type, language=language
        )
    except LocalVoiceError as exc:
        return JsonResponse({"error": "voice_unavailable", "detail": str(exc)}, status=503)
    _audit_voice(request, school, "transcribe", str(language), len(request.body))
    response = JsonResponse({"text": text, "retained": False})
    response["Cache-Control"] = "no-store"
    return response


@require_POST
@login_required_api
def local_voice_synthesize_view(request):
    school, error = _tenant_required(request)
    if error:
        return error
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)
    if not _consent(request, body):
        return JsonResponse({"error": "explicit_consent_required"}, status=400)
    limited = _voice_rate_limit(request, school)
    if limited:
        return limited
    language = body.get("language", "en")
    try:
        audio = synthesize(body.get("text", ""), language=language)
    except LocalVoiceError as exc:
        return JsonResponse({"error": "voice_unavailable", "detail": str(exc)}, status=503)
    _audit_voice(request, school, "synthesize", str(language), len(request.body))
    response = HttpResponse(audio.body, content_type=audio.content_type)
    response["Cache-Control"] = "no-store"
    response["X-Content-Retained"] = "false"
    return response
