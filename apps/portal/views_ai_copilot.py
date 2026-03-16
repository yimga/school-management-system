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

from apps.accounts.utils import get_user_role
from apps.compliance.models import AuditLog
from django.core.cache import cache
from apps.portal.ai_provider import (
    generate_ai_response,
    get_public_ai_provider_status,
)
from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    log_view_exception,
    request_context_for_log,
)
from apps.siteconfig.cache_utils import tenant_cache_key

logger = logging.getLogger(__name__)
AI_COPILOT_ENABLED = getattr(settings, "AI_COPILOT_ENABLED", True)

# --- AI Copilot Rate Limiting & Telemetry ---
RATE_LIMIT_PER_MIN = int(os.environ.get('AI_COPILOT_RATE_LIMIT', '30'))
RATE_LIMIT_WINDOW = int(os.environ.get('AI_COPILOT_RATE_WINDOW', '60'))  # seconds


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
            user_agent=(request.META.get('HTTP_USER_AGENT', '') or '')[:500],
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
        retry_after = max(0, int(RATE_LIMIT_WINDOW - (now - events[0]))) if events else RATE_LIMIT_WINDOW
        return False, retry_after
    # Allow and record this event
    events.append(now)
    _cache_set(key, events, RATE_LIMIT_WINDOW)
    return True, 0


def _increment_usage_metrics(user, allowed: bool, request=None):
    """Increment simple counters in cache for lightweight telemetry (tenant-scoped keys)."""
    def _k(b):
        return tenant_cache_key(b, request)

    _cache_incr_or_set(_k('ai_copilot_usage_total'))

    role = get_user_role(user) or 'USER'
    roles = _cache_get(_k('ai_copilot_usage_roles'), []) or []
    if not isinstance(roles, list):
        roles = []
    if role and role not in roles:
        roles.append(role)
        _cache_set(_k('ai_copilot_usage_roles'), roles, None)

    _cache_incr_or_set(_k(f'ai_copilot_usage_role:{role}'))

    if not allowed:
        _cache_incr_or_set(_k('ai_copilot_usage_denied_total'))


def get_ai_permissions(user):
    """
    Determine what AI copilot features are available for the user's role.
    Returns a dict of available features and scopes.
    """
    role = get_user_role(user) or 'USER'
    admin_roles = {"ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "IT_ADMIN"}
    admin_roles | {"BURSAR"}
    is_admin_like = user.is_superuser or user.is_staff or role in admin_roles

    permissions = {
        'can_access_ai': user.is_authenticated,
        'can_analyze_data': False,
        'can_view_financial': False,
        'can_view_compliance': False,
        'can_access_grades': False,
        'can_access_roster': False,
        'scope': 'general',
    }

    if is_admin_like:
        permissions.update({
            'can_analyze_data': True,
            'can_view_financial': True,
            'can_view_compliance': True,
            'can_access_grades': True,
            'can_access_roster': True,
            'scope': 'admin',
        })
    elif role == 'BURSAR':
        permissions.update({
            'can_analyze_data': True,
            'can_view_financial': True,
            'scope': 'finance',
        })
    elif role == 'TEACHER':
        permissions.update({
            'can_access_grades': True,
            'can_access_roster': True,
            'scope': 'teacher',
        })
    elif role == 'PARENT':
        permissions.update({
            'can_access_grades': True,  # Only their child's grades
            'can_view_financial': True,  # Only their child's fees
            'scope': 'parent',
        })
    
    return permissions


def is_query_allowed(user, query):
    """
    First-line validation using keyword heuristics. Do not rely on this alone for security:
    all data returned by the AI/data layer must be scoped by role and ownership (e.g. parent
    sees only their children, teacher only their classes). Keyword checks can be bypassed;
    enforce server-side data scoping in the code that builds context and answers.
    Returns: (bool, str) - (is_allowed, denial_reason)
    """
    permissions = get_ai_permissions(user)
    
    if not permissions['can_access_ai']:
        return False, "You are not authenticated to use AI Copilot."
    
    query_lower = query.lower()
    
    # Keyword-based restrictions
    financial_keywords = ['invoice', 'payment', 'fee', 'financial']
    payroll_keywords = ['salary', 'payroll']
    compliance_keywords = ['audit', 'compliance', 'permission', 'access log', 'security']
    all_grades_keywords = ['all grades', 'all students grade', 'every student']
    
    if any(kw in query_lower for kw in payroll_keywords):
        if permissions.get('scope') not in {'admin', 'finance'}:
            return False, "You don't have permission to access payroll data."

    if any(kw in query_lower for kw in financial_keywords):
        if not permissions['can_view_financial']:
            return False, "You don't have permission to access financial data."
    
    if any(kw in query_lower for kw in compliance_keywords):
        if not permissions['can_view_compliance']:
            return False, "You don't have permission to access compliance data."
    
    if any(kw in query_lower for kw in all_grades_keywords):
        if permissions['scope'] == 'parent':
            return False, "Parents can only view their child's grades, not all students."
        if permissions['scope'] == 'teacher' and 'all' in query_lower:
            return False, "Teachers can only view their own classes' grades."
    
    return True, ""


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
        data = json.loads(request.body)
        user_query = data.get('query', '').strip()

        # Rate limit per user before processing
        allowed_rl, retry_after = _check_rate_limit(request.user, request)
        if not allowed_rl:
            _log_ai_audit(
                request,
                AuditLog.Action.ACCESS_DENIED,
                reason="Rate limit exceeded",
                details={
                    'event': 'AI_QUERY_RATE_LIMITED',
                    'query': user_query[:100],
                    'retry_after': retry_after,
                    'limit': RATE_LIMIT_PER_MIN,
                },
                sensitivity=AuditLog.Sensitivity.MEDIUM,
            )
            _increment_usage_metrics(request.user, allowed=False, request=request)
            return JsonResponse({
                'success': False,
                'error': 'Rate limit exceeded. Please wait a moment and try again.',
                'retry_after': retry_after,
            }, status=429)
        
        if not user_query:
            return JsonResponse({
                'success': False,
                'error': 'Query cannot be empty.'
            }, status=400)
        
        # Validate query is allowed for this user
        is_allowed, denial_reason = is_query_allowed(request.user, user_query)
        
        if not is_allowed:
            # Log the denied attempt
            _log_ai_audit(
                request,
                AuditLog.Action.ACCESS_DENIED,
                reason=denial_reason,
                details={
                    'event': 'AI_QUERY_DENIED',
                    'query': user_query[:100],  # Store first 100 chars
                    'reason': denial_reason,
                },
                sensitivity=AuditLog.Sensitivity.MEDIUM,
            )
            
            _increment_usage_metrics(request.user, allowed=False, request=request)
            return JsonResponse({
                'success': False,
                'error': denial_reason
            }, status=403)
        
        # Log successful query
        _log_ai_audit(
            request,
            AuditLog.Action.VIEW,
            reason="AI Copilot query submitted",
            details={
                'event': 'AI_QUERY_SUBMITTED',
                'query': user_query[:100],
                'role': getattr(request.user, 'role', 'USER'),
            },
            sensitivity=AuditLog.Sensitivity.LOW,
        )
        
        # Build contextual prompt and call configured provider chain
        permissions = get_ai_permissions(request.user)
        prompt = build_contextual_prompt(request.user, user_query)
        response_text, provider_meta = generate_ai_response(
            prompt,
            user_query=user_query,
            metadata={
                "user_id": getattr(request.user, "id", None),
                "role": getattr(request.user, "role", "USER"),
                # Keep tenant metadata out of prompt/provider payload.
                "school_id": getattr(getattr(request, "school", None), "id", None),
            },
        )

        _increment_usage_metrics(request.user, allowed=True, request=request)
        _cache_set(tenant_cache_key('ai_copilot_last_success_ts', request), time.time(), None)
        return JsonResponse({
            'success': True,
            'allowed': True,
            'permissions': permissions,
            'user_role': getattr(request.user, 'role', 'USER'),
            'response': response_text,
            'provider': provider_meta.get("provider"),
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body.'
        }, status=400)
    except (DatabaseError, OSError, RuntimeError, TypeError, ValueError) as e:
        log_view_exception(request, "portal.views_ai_copilot: AI Copilot error", extra={"error": str(e)})
        _cache_incr_or_set(tenant_cache_key('ai_copilot_usage_errors_total', request))
        _cache_set(tenant_cache_key('ai_copilot_last_error_ts', request), time.time(), None)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred processing your request.'
        }, status=500)


def get_client_ip(request):
    """
    Extract client IP from request, accounting for proxies.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


@login_required
def ai_permissions(request):
    """
    Return user's AI permissions without processing a query.
    Useful for frontend to show/hide features conditionally.
    """
    permissions = get_ai_permissions(request.user)
    return JsonResponse({
        'success': True,
        'permissions': permissions,
        'user_role': getattr(request.user, 'role', 'USER'),
    })


@require_GET
@login_required
def ai_copilot_limits(request):
    """Return current rate limit status for the logged-in user (tenant-scoped)."""
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
    return JsonResponse({
        'success': True,
        'rate_limit': RATE_LIMIT_PER_MIN,
        'window_seconds': RATE_LIMIT_WINDOW,
        'used': used,
        'remaining': remaining,
        'reset_in_seconds': reset_in,
    })


@require_GET
@login_required
def ai_copilot_config(request):
    """Return AI Copilot backend config visibility for frontend widgets."""
    status = get_public_ai_provider_status()
    enabled = bool(status.get("has_live_provider")) or bool(status.get("rules_fallback_enabled"))
    model = None
    providers = status.get("providers", {})
    for provider in status.get("preference", []):
        provider_state = providers.get(provider, {})
        if provider == "ollama" and provider_state.get("configured"):
            model = provider_state.get("model")
            break
        if provider == "gemini" and provider_state.get("configured"):
            model = provider_state.get("model")
            break
        if provider == "rules":
            model = "rules-fallback"
            break
    return JsonResponse({
        'success': True,
        'enabled': enabled,
        'model': model,
        'provider_status': status,
        'rate_limit': RATE_LIMIT_PER_MIN,
        'window_seconds': RATE_LIMIT_WINDOW,
        'user_role': (getattr(request.user, 'role', 'USER') or '').upper(),
    })


@require_GET
@login_required
def ai_copilot_audit_feed(request):
    """Return recent AI-related audit logs; staff/admin only."""
    user = request.user
    role_value = get_user_role(user)
    if not (user.is_staff or user.is_superuser or role_value in ('ADMIN', 'LEADERSHIP', 'PRINCIPAL', 'VICE_PRINCIPAL', 'DEAN', 'IT_ADMIN')):
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    try:
        limit = int(request.GET.get('limit', '20'))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 20

    actions = ['AI_QUERY_SUBMITTED', 'AI_QUERY_DENIED', 'AI_QUERY_RATE_LIMITED']
    # Minimal fields to avoid leaking sensitive data
    qs = AuditLog.objects.filter(action__in=actions).order_by('-timestamp')[:limit]
    items = []
    for row in qs:
        items.append({
            'id': getattr(row, 'id', None),
            'action': getattr(row, 'action', ''),
            'when': getattr(row, 'timestamp', None).isoformat() if getattr(row, 'timestamp', None) else None,
            'user': getattr(getattr(row, 'user', None), 'username', None),
            'details': getattr(row, 'details', {}),
            'severity': getattr(row, 'severity', 'INFO'),
        })
    return JsonResponse({'success': True, 'items': items})


def build_contextual_prompt(user, user_message: str) -> str:
    """
    Build a role-aware prompt for the AI backend.
    """
    user_name = getattr(user, 'first_name', '') or getattr(user, 'username', 'User')
    role = get_user_role(user) or 'USER'
    admin_roles = {"ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "IT_ADMIN"}
    is_admin_like = user.is_superuser or user.is_staff or role in admin_roles
    context = "You are an AI assistant for a school management system. "

    if is_admin_like:
        context += (
            f"The user is an administrator named {user_name}. "
            "Help with system analytics, user management, financial summaries, compliance tasks, and administrative operations. "
        )
    elif role == 'BURSAR':
        context += (
            f"The user is a finance officer named {user_name}. "
            "Help with fee collection, invoice status, payment reconciliation, and finance reporting. "
        )
    elif role == 'TEACHER':
        context += (
            f"The user is a teacher named {user_name}. "
            "Help with grade entry, class roster information, attendance tracking, student performance insights, and lesson planning. "
        )
    elif role == 'PARENT':
        context += (
            f"The user is a parent named {user_name}. "
            "Focus responses on their child's information only, including progress, fee payment status, communication with teachers, and school events. "
        )
    else:
        context += (
            f"The user is {user_name}. Help with general system navigation and common tasks. "
        )

    context += (
        "Keep responses concise (2-3 sentences max), helpful, and professional. "
        "IMPORTANT: Only provide information the user has access to. "
        f"User question: {user_message}"
    )
    return context
