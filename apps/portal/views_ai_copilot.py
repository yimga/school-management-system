"""
AI Copilot Backend Views - RBAC Protected
Handles AI requests with role-based access control and audit logging.
"""

import json
import logging
import os
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import User
from apps.accounts.utils import get_user_role
from apps.compliance.models import AuditLog
from django.core.cache import cache
from apps.portal.ai_provider import (
    generate_ai_response,
    get_ai_provider_status,
    get_public_ai_provider_status,
    probe_ai_provider_reachable,
)
from services.ai_helpers import normalize_gateway_metadata
from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    log_view_exception,
    request_context_for_log,
)
from apps.siteconfig.cache_utils import tenant_cache_key

logger = logging.getLogger(__name__)
AI_COPILOT_ENABLED = getattr(settings, "AI_COPILOT_ENABLED", True)

# --- AI Copilot Rate Limiting & Telemetry ---
RATE_LIMIT_PER_MIN = int(os.environ.get("AI_COPILOT_RATE_LIMIT", "30"))
RATE_LIMIT_WINDOW = int(os.environ.get("AI_COPILOT_RATE_WINDOW", "60"))  # seconds


def _cache_get(key, default=None):
    try:
        return cache.get(key, default)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        logger.debug("AI copilot cache get failed for %s", key, exc_info=True)
        return default


def _cache_set(key, value, timeout=None):
    try:
        cache.set(key, value, timeout)
        return True
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        logger.debug("AI copilot cache set failed for %s", key, exc_info=True)
        return False


def _cache_incr_or_set(key, amount: int = 1):
    try:
        cache.incr(key, amount)
        return True
    except (ValueError, TypeError):
        return _cache_set(key, amount, None)
    except (AttributeError, OSError, RuntimeError):
        logger.debug("AI copilot cache incr failed for %s", key, exc_info=True)
        return False


def _log_ai_audit(request, action, reason="", details=None, sensitivity=None):
    """Best-effort audit logging for AI copilot events."""
    try:
        AuditLog.objects.create(
            user=getattr(request, "user", None),
            ip_address=get_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:500],
            action=action,
            model_name="AICopilot",
            object_id=str(getattr(getattr(request, "user", None), "id", "")),
            object_repr="AI Copilot Query",
            app_label="portal",
            reason=(reason or "")[:255],
            sensitivity=sensitivity or AuditLog.Sensitivity.MEDIUM,
            new_values=details or {},
        )
    except DatabaseError:
        # Avoid blocking AI responses if audit logging fails
        ctx = request_context_for_log(request) if request else {}
        log_exception_with_context(
            "AI Copilot audit logging failed",
            exc_info=True,
            **ctx,
        )


def _check_rate_limit(user, request=None):
    """Simple per-user sliding window rate limiter using Django cache (tenant-scoped)."""
    base = f"ai_rl:{getattr(user, 'id', 'anon')}"
    key = tenant_cache_key(base, request)
    now = time.time()
    events = _cache_get(key, [])
    if not isinstance(events, (list, tuple)):
        events = []
    # Keep only events within window
    events = [t for t in events if now - t < RATE_LIMIT_WINDOW]
    if len(events) >= RATE_LIMIT_PER_MIN:
        # Save pruned events and deny
        _cache_set(key, events, RATE_LIMIT_WINDOW)
        # Calculate approximate seconds until next allowed (based on oldest event)
        retry_after = (
            max(0, int(RATE_LIMIT_WINDOW - (now - events[0])))
            if events
            else RATE_LIMIT_WINDOW
        )
        return False, retry_after
    # Allow and record this event
    events.append(now)
    _cache_set(key, events, RATE_LIMIT_WINDOW)
    return True, 0


def _increment_usage_metrics(user, allowed: bool, request=None):
    """Increment simple counters in cache for lightweight telemetry (tenant-scoped keys)."""

    def _k(b):
        return tenant_cache_key(b, request)

    _cache_incr_or_set(_k("ai_copilot_usage_total"))

    role = get_user_role(user) or "USER"
    roles = _cache_get(_k("ai_copilot_usage_roles"), []) or []
    if not isinstance(roles, list):
        roles = []
    if role and role not in roles:
        roles.append(role)
        _cache_set(_k("ai_copilot_usage_roles"), roles, None)

    _cache_incr_or_set(_k(f"ai_copilot_usage_role:{role}"))

    if not allowed:
        _cache_incr_or_set(_k("ai_copilot_usage_denied_total"))


def _is_copilot_admin_like(user) -> bool:
    """Platform operators (manager SUPERADMIN) get admin copilot scope."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    role = (get_user_role(user) or "").upper()
    admin_roles = {
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "IT_ADMIN",
        "SUPERADMIN",
    }
    if role in admin_roles:
        return True
    try:
        from apps.schools.control_plane import user_has_control_plane_access

        return user_has_control_plane_access(user)
    except ImportError:
        return False


def get_ai_permissions(user):
    """
    Determine what AI copilot features are available for the user's role.
    Returns a dict of available features and scopes.
    """
    from services.ai_copilot_rbac import build_copilot_permissions

    return build_copilot_permissions(user)


def is_query_allowed(user, query):
    """
    First-line validation using keyword heuristics. Do not rely on this alone for security:
    all data returned by the AI/data layer must be scoped by role and ownership (e.g. parent
    sees only their children, teacher only their classes). Keyword checks can be bypassed;
    enforce server-side data scoping in the code that builds context and answers.
    Returns: (bool, str) - (is_allowed, denial_reason)
    """
    from services.ai_copilot_rbac import build_copilot_permissions, validate_copilot_query

    permissions = get_ai_permissions(user)
    return validate_copilot_query(
        user,
        query,
        permissions,
        school=None,
        task_type="general_chat",
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def ai_copilot_query(request):
    """
    Backend endpoint for AI Copilot queries.

    Validates user permissions before processing.
    Logs all requests for audit purposes.
    """
    if not AI_COPILOT_ENABLED:
        return JsonResponse(
            {"success": False, "error": "AI Copilot is disabled."},
            status=503,
        )
    try:
        from apps.portal.ai_chrome_config import ai_copilot_query_api_enabled_for_request

        if not ai_copilot_query_api_enabled_for_request(request):
            return JsonResponse(
                {"success": False, "error": "AI Copilot API is disabled for this tenant."},
                status=503,
            )
    except (AttributeError, ImportError, TypeError, ValueError):
        pass
    try:
        from services.ai_copilot_rbac import (
            build_copilot_permissions,
            rbac_directives_for_permissions,
            validate_copilot_query,
        )

        data = json.loads(request.body)
        user_query = data.get("query", "").strip()

        # Rate limit per user before processing
        allowed_rl, retry_after = _check_rate_limit(request.user, request)
        if not allowed_rl:
            _log_ai_audit(
                request,
                AuditLog.Action.ACCESS_DENIED,
                reason="Rate limit exceeded",
                details={
                    "event": "AI_QUERY_RATE_LIMITED",
                    "query": user_query[:100],
                    "retry_after": retry_after,
                    "limit": RATE_LIMIT_PER_MIN,
                },
                sensitivity=AuditLog.Sensitivity.MEDIUM,
            )
            _increment_usage_metrics(request.user, allowed=False, request=request)
            return JsonResponse(
                {
                    "success": False,
                    "error": "Rate limit exceeded. Please wait a moment and try again.",
                    "retry_after": retry_after,
                },
                status=429,
            )

        if not user_query:
            return JsonResponse(
                {"success": False, "error": "Query cannot be empty."}, status=400
            )

        # Validate query is allowed for this user
        permissions = build_copilot_permissions(request.user, request=request)
        is_allowed, denial_reason = validate_copilot_query(
            request.user,
            user_query,
            permissions,
            school=getattr(request, "school", None),
            task_type="general_chat",
        )

        if not is_allowed:
            # Log the denied attempt
            _log_ai_audit(
                request,
                AuditLog.Action.ACCESS_DENIED,
                reason=denial_reason,
                details={
                    "event": "AI_QUERY_DENIED",
                    "query": user_query[:100],  # Store first 100 chars
                    "reason": denial_reason,
                },
                sensitivity=AuditLog.Sensitivity.MEDIUM,
            )

            _increment_usage_metrics(request.user, allowed=False, request=request)
            return JsonResponse({"success": False, "error": denial_reason}, status=403)

        # Log successful query
        _log_ai_audit(
            request,
            AuditLog.Action.VIEW,
            reason="AI Copilot query submitted",
            details={
                "event": "AI_QUERY_SUBMITTED",
                "query": user_query[:100],
                "role": getattr(request.user, "role", "USER"),
            },
            sensitivity=AuditLog.Sensitivity.LOW,
        )

        # Build contextual prompt and call configured provider chain
        from apps.portal.ai_surface_context import build_ai_surface_context

        surface = build_ai_surface_context(request)
        directives = rbac_directives_for_permissions(
            permissions,
            active_url=str(surface.get("current_path") or ""),
            host_kind=getattr(request, "public_host_kind", None),
        )
        prompt = build_contextual_prompt(
            request.user,
            user_query,
            current_path=surface.get("current_path") or "",
        )
        prompt = f"{directives}\n\n{prompt}"
        rag_block = ""
        try:
            from services.ai_memory import AIMemoryService, get_embedding_for_text

            from apps.portal.views_ai_gateway import _retrieval_kwargs, _school_id

            sid = _school_id(request)
            if sid:
                emb = get_embedding_for_text(user_query, max_tokens=512)
                if emb:
                    parts: list[str] = []
                    for scope in ("help", "config", "default"):
                        for r in AIMemoryService.search_similar(
                            sid, scope, emb, limit=2, **_retrieval_kwargs(request)
                        ):
                            parts.append(str(r.get("metadata", ""))[:400])
                    rag_block = "\n".join(parts)[:1200]  # magic-number-allow: ai-message-char-cap
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            DatabaseError,
        ):
            rag_block = ""
        if rag_block:
            prompt = (
                "Use the following retrieved internal snippets when they are relevant "
                "(do not invent facts beyond them or the user's question):\n"
                f"{rag_block}\n\n"
                f"{prompt}"
            )
        response_text, provider_meta = generate_ai_response(
            prompt,
            user_query=user_query,
            metadata=normalize_gateway_metadata(
                {
                    "request": request,
                    "school": getattr(request, "school", None),
                    "user_id": getattr(request.user, "id", None),
                    "role": getattr(request.user, "role", "USER"),
                    "permissions": permissions,
                    "rbac_scope": permissions.get("scope"),
                    "copilot_rbac_enforced": True,
                    **surface,
                }
            ),
        )

        _increment_usage_metrics(request.user, allowed=True, request=request)
        _cache_set(
            tenant_cache_key("ai_copilot_last_success_ts", request), time.time(), None
        )
        return JsonResponse(
            {
                "success": True,
                "allowed": True,
                "permissions": permissions,
                "user_role": getattr(request.user, "role", "USER"),
                "response": response_text,
                "provider": provider_meta.get("provider"),
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON in request body."}, status=400
        )
    except (DatabaseError, OSError, RuntimeError, TypeError, ValueError) as e:
        log_view_exception(
            request,
            "portal.views_ai_copilot: AI Copilot error",
            extra={"error": str(e)},
        )
        _cache_incr_or_set(tenant_cache_key("ai_copilot_usage_errors_total", request))
        _cache_set(
            tenant_cache_key("ai_copilot_last_error_ts", request), time.time(), None
        )
        return JsonResponse(
            {"success": False, "error": "An error occurred processing your request."},
            status=500,
        )


def get_client_ip(request):
    """
    Extract client IP from request, accounting for proxies.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip


@login_required
def ai_permissions(request):
    """
    Return user's AI permissions without processing a query.
    Useful for frontend to show/hide features conditionally.
    """
    permissions = get_ai_permissions(request.user)
    return JsonResponse(
        {
            "success": True,
            "permissions": permissions,
            "user_role": getattr(request.user, "role", "USER"),
        }
    )


@require_GET
@login_required
def ai_copilot_limits(request):
    """Return current rate limit status for the logged-in user (tenant-scoped)."""
    try:
        from apps.platform_runtime.helpers import log_ai_action

        school = getattr(request, "school", None)
        log_ai_action(
            "ai_copilot:limits_fetch",
            tenant_id=str(school.pk) if school else None,
            user_id=request.user.pk,
            request_id=getattr(request, "request_id", None),
            payload={},
        )
    except (OSError, TypeError, ValueError, AttributeError):
        pass
    key = tenant_cache_key(f"ai_rl:{getattr(request.user, 'id', 'anon')}", request)
    now = time.time()
    events = _cache_get(key, [])
    if not isinstance(events, (list, tuple)):
        events = []
    events = [t for t in events if now - t < RATE_LIMIT_WINDOW]
    used = len(events)
    remaining = max(0, RATE_LIMIT_PER_MIN - used)
    reset_in = 0
    if events:
        reset_in = max(0, int(RATE_LIMIT_WINDOW - (now - events[0])))
    return JsonResponse(
        {
            "success": True,
            "rate_limit": RATE_LIMIT_PER_MIN,
            "window_seconds": RATE_LIMIT_WINDOW,
            "used": used,
            "remaining": remaining,
            "reset_in_seconds": reset_in,
        }
    )


@require_GET
@login_required
def ai_copilot_config(request):
    """Return AI Copilot backend config visibility for frontend widgets."""
    status = get_public_ai_provider_status()
    enabled = bool(status.get("has_live_provider")) or bool(
        status.get("rules_fallback_enabled")
    )
    model = None
    providers = status.get("providers", {})
    if status.get("live_provider_kind") == "cloud":
        litellm_state = providers.get("litellm", {})
        if litellm_state.get("configured"):
            model = litellm_state.get("model")
    if model is None:
        for provider in status.get("preference", []):
            provider_state = providers.get(provider, {})
            if provider == "ollama" and provider_state.get("configured"):
                model = provider_state.get("model")
                break
            if provider == "rules":
                model = "rules-fallback"
                break
    try:
        from apps.platform_runtime.helpers import log_ai_action

        school = getattr(request, "school", None)
        log_ai_action(
            "ai_copilot:config_fetch",
            tenant_id=str(school.pk) if school else None,
            user_id=request.user.pk,
            request_id=getattr(request, "request_id", None),
            payload={"enabled": enabled, "model": model},
        )
    except (OSError, TypeError, ValueError, AttributeError):
        pass
    return JsonResponse(
        {
            "success": True,
            "enabled": enabled,
            "model": model,
            "provider_status": status,
            "rate_limit": RATE_LIMIT_PER_MIN,
            "window_seconds": RATE_LIMIT_WINDOW,
            "user_role": (getattr(request.user, "role", "USER") or "").upper(),
        }
    )


@require_GET
@login_required
def ai_health(request):
    """
    Phase E (2026-05-12): lightweight AI health endpoint for the copilot UI.

    Returns reachable / provider / latency / fallback_active / degraded so the
    floating AI Copilot can show a visible "limited mode" badge instead of failing
    silently when Ollama is down. Cached for 60s server-side.
    """
    health = probe_ai_provider_reachable()
    status = get_ai_provider_status()
    reachable = bool(health.get("reachable"))
    payload = {
        "success": True,
        "reachable": reachable,
        "provider": health.get("provider", "none"),
        "latency_ms": health.get("latency_ms"),
        "fallback_active": bool(health.get("fallback_active")),
        "degraded": bool(health.get("degraded")),
        "checked_at": health.get("checked_at"),
        "ollama_configured": bool(status.get("ollama_configured")),
        "preference": status.get("preference", []),
        "rules_fallback_enabled": bool(status.get("rules_fallback_enabled")),
        "deployment_profile": health.get("deployment_profile"),
        "litellm_configured": health.get("litellm_configured"),
        "posture_mode": health.get("posture_mode"),
        "posture_label": health.get("posture_label"),
        "live_provider_kind": health.get("live_provider_kind"),
        "gateway_tier_chain": health.get("gateway_tier_chain"),
    }
    return JsonResponse(payload)


@require_GET
@login_required
def ai_copilot_audit_feed(request):
    """Return recent AI-related audit logs; staff/admin only."""
    user = request.user
    role_value = get_user_role(user)
    if not (
        user.is_staff
        or user.is_superuser
        or role_value
        in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "IT_ADMIN")  # role-string-allow: rbac-role-comparison
    ):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    try:
        limit = int(request.GET.get("limit", "20"))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 20

    actions = ["AI_QUERY_SUBMITTED", "AI_QUERY_DENIED", "AI_QUERY_RATE_LIMITED"]
    # Minimal fields to avoid leaking sensitive data
    qs = AuditLog.objects.filter(action__in=actions).order_by("-timestamp")[:limit]
    items = []
    for row in qs:
        items.append(
            {
                "id": getattr(row, "id", None),
                "action": getattr(row, "action", ""),
                "when": getattr(row, "timestamp", None).isoformat()
                if getattr(row, "timestamp", None)
                else None,
                "user": getattr(getattr(row, "user", None), "username", None),
                "details": getattr(row, "details", {}),
                "severity": getattr(row, "severity", "INFO"),
            }
        )
    return JsonResponse({"success": True, "items": items})


def build_contextual_prompt(
    user,
    user_message: str,
    *,
    current_path: str = "",
) -> str:
    """
    Build a role-aware prompt for the AI backend.
    """
    user_name = getattr(user, "first_name", "") or getattr(user, "username", "User")
    role = get_user_role(user) or "USER"
    admin_roles = {
        "ADMIN",  # role-string-allow: rbac-role-comparison
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "IT_ADMIN",
    }
    is_admin_like = user.is_superuser or user.is_staff or role in admin_roles
    context = "You are an AI assistant for a school management system. "

    if is_admin_like:
        context += (
            f"The user is an administrator named {user_name}. "
            "Help with system analytics, user management, financial summaries, compliance tasks, and administrative operations. "
        )
    elif role == "BURSAR":
        context += (
            f"The user is a finance officer named {user_name}. "
            "Help with fee collection, invoice status, payment reconciliation, and finance reporting. "
        )
    elif role == User.Role.TEACHER:
        context += (
            f"The user is a teacher named {user_name}. "
            "Help with grade entry, class roster information, attendance tracking, student performance insights, and lesson planning. "
        )
    elif role == User.Role.PARENT:
        context += (
            f"The user is a parent named {user_name}. "
            "Focus responses on their child's information only, including progress, fee payment status, communication with teachers, and school events. "
        )
    elif role == User.Role.STUDENT:
        context += (
            f"The user is a student named {user_name}. "
            "Help with their own grades, assignments, schedule, and school navigation only — never other students or staff records. "
        )
    else:
        context += f"The user is {user_name}. Help with general system navigation and common tasks. "

    path_hint = (current_path or "").strip()
    if path_hint:
        context += f"The user is on screen {path_hint}. Prefer guidance relevant to that route. "
    context += (
        "Keep responses concise (2-3 sentences max), helpful, and professional. "
        "IMPORTANT: Only provide information the user has access to. "
        f"User question: {user_message}"
    )
    return context
