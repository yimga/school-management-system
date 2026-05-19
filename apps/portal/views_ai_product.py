"""Product-tier AI endpoints (settings, import resolver, reports, tours)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.portal.views_ai_gateway import (
    GATEWAY_VIEW_ERRORS,
    _gateway_rate_limit,
    _log_gateway_audit,
    log_view_exception,
)
from services.ai.product_assistants import (
    guardrail_report_recommend,
    plan_guided_tour,
    resolve_import_errors,
    smart_settings_assist,
)


def _school(request):
    return getattr(request, "school", None)


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_smart_settings_assistant(request):
    """POST: { query, active_url? } → engine-room settings guidance."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:2000]
        active_url = (body.get("active_url") or body.get("path") or "").strip()[:500]
        if not query:
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        engine = smart_settings_assist(
            request.user, query, school=_school(request), active_url=active_url
        )
        _log_gateway_audit(
            request,
            "smart_settings_assistant",
            "config_explain",
            "success" if engine.get("success") else "degraded",
            engine.get("meta") or {},
        )
        return JsonResponse(
            {
                "success": bool(engine.get("success")),
                "response": engine.get("response") or "",
                "escalation_required": bool(engine.get("escalation_required")),
                "meta": engine.get("meta") or {},
            }
        )
    except GATEWAY_VIEW_ERRORS as exc:
        log_view_exception(request, "smart_settings_assistant", exc)
        return JsonResponse({"success": False, "error": "unavailable"}, status=503)


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_import_error_resolver(request):
    """POST: { errors: [{row, field, message}], import_kind? } → fix steps."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        errors = body.get("errors") or body.get("validation_errors") or []
        if not isinstance(errors, list):
            return JsonResponse({"success": False, "error": "errors must be a list"}, status=400)
        import_kind = str(body.get("import_kind") or body.get("domain") or "").strip()[:80]
        out = resolve_import_errors(
            request.user, errors, school=_school(request), import_kind=import_kind
        )
        _log_gateway_audit(
            request,
            "import_error_resolver",
            "support_suggest",
            "success",
            out.get("meta") or {},
        )
        return JsonResponse(out)
    except GATEWAY_VIEW_ERRORS as exc:
        log_view_exception(request, "import_error_resolver", exc)
        return JsonResponse({"success": False, "error": "unavailable"}, status=503)


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_guardrail_report_generator(request):
    """POST: { query } → permission-aware report recommendations."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1000]
        if not query:
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        out = guardrail_report_recommend(request.user, query, school=_school(request))
        _log_gateway_audit(
            request,
            "guardrail_report_generator",
            "setup_recommend",
            "success",
            out.get("meta") or {},
        )
        return JsonResponse(out)
    except GATEWAY_VIEW_ERRORS as exc:
        log_view_exception(request, "guardrail_report_generator", exc)
        return JsonResponse({"success": False, "error": "unavailable"}, status=503)


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_guided_tour_planner(request):
    """POST: { goal, active_url? } → tour steps + narrative."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        goal = (body.get("goal") or body.get("query") or "").strip()[:1000]
        active_url = (body.get("active_url") or body.get("path") or "").strip()[:500]
        if not goal:
            return JsonResponse({"success": False, "error": "goal required"}, status=400)
        out = plan_guided_tour(
            request.user, goal, school=_school(request), active_url=active_url
        )
        _log_gateway_audit(
            request,
            "guided_tour_planner",
            "setup_recommend",
            "success",
            out.get("meta") or {},
        )
        return JsonResponse(out)
    except GATEWAY_VIEW_ERRORS as exc:
        log_view_exception(request, "guided_tour_planner", exc)
        return JsonResponse({"success": False, "error": "unavailable"}, status=503)
