"""
AI Copilot Backend Views - RBAC Protected
Handles AI requests with role-based access control and audit logging.
"""
import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods, require_GET
from django.views.decorators.csrf import csrf_protect
from apps.compliance.models import AuditLog
from django.core.cache import cache
import time
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# --- AI Copilot Rate Limiting & Telemetry ---
RATE_LIMIT_PER_MIN = int(os.environ.get('AI_COPILOT_RATE_LIMIT', '30'))
RATE_LIMIT_WINDOW = int(os.environ.get('AI_COPILOT_RATE_WINDOW', '60'))  # seconds


def _check_rate_limit(user):
    """Simple per-user sliding window rate limiter using Django cache."""
    key = f"ai_rl:{getattr(user, 'id', 'anon')}"
    now = time.time()
    events = cache.get(key, [])
    # Keep only events within window
    events = [t for t in events if now - t < RATE_LIMIT_WINDOW]
    if len(events) >= RATE_LIMIT_PER_MIN:
        # Save pruned events and deny
        cache.set(key, events, RATE_LIMIT_WINDOW)
        # Calculate approximate seconds until next allowed (based on oldest event)
        retry_after = max(0, int(RATE_LIMIT_WINDOW - (now - events[0]))) if events else RATE_LIMIT_WINDOW
        return False, retry_after
    # Allow and record this event
    events.append(now)
    cache.set(key, events, RATE_LIMIT_WINDOW)
    return True, 0


def _increment_usage_metrics(user, allowed: bool):
    """Increment simple counters in cache for lightweight telemetry."""
    try:
        cache.incr('ai_copilot_usage_total')
    except ValueError:
        cache.set('ai_copilot_usage_total', 1, None)

    role = getattr(user, 'role', 'USER')
    # Track seen roles for metrics endpoint
    try:
        roles = cache.get('ai_copilot_usage_roles') or []
        if role not in roles:
            roles.append(role)
            cache.set('ai_copilot_usage_roles', roles, None)
    except Exception:
        pass

    try:
        cache.incr(f'ai_copilot_usage_role:{role}')
    except ValueError:
        cache.set(f'ai_copilot_usage_role:{role}', 1, None)

    if not allowed:
        try:
            cache.incr('ai_copilot_usage_denied_total')
        except ValueError:
            cache.set('ai_copilot_usage_denied_total', 1, None)


def get_ai_permissions(user):
    """
    Determine what AI copilot features are available for the user's role.
    Returns a dict of available features and scopes.
    """
    role = getattr(user, 'role', 'USER')
    
    permissions = {
        'can_access_ai': user.is_authenticated,
        'can_analyze_data': False,
        'can_view_financial': False,
        'can_view_compliance': False,
        'can_access_grades': False,
        'can_access_roster': False,
        'scope': 'general',
    }
    
    if role in ['ADMIN', 'LEADERSHIP']:
        permissions.update({
            'can_analyze_data': True,
            'can_view_financial': True,
            'can_view_compliance': True,
            'can_access_grades': True,
            'can_access_roster': True,
            'scope': 'admin',
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
            'scope': 'parent',
        })
    
    return permissions


def is_query_allowed(user, query):
    """
    Validate that the user's query doesn't request data they don't have access to.
    
    Returns: (bool, str) - (is_allowed, denial_reason)
    """
    permissions = get_ai_permissions(user)
    
    if not permissions['can_access_ai']:
        return False, "You are not authenticated to use AI Copilot."
    
    query_lower = query.lower()
    
    # Keyword-based restrictions
    financial_keywords = ['invoice', 'payment', 'fee', 'salary', 'payroll', 'financial']
    compliance_keywords = ['audit', 'compliance', 'permission', 'access log', 'security']
    all_grades_keywords = ['all grades', 'all students grade', 'every student']
    
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
@login_required(login_url='/authentication/login/')
def ai_copilot_query(request):
    """
    Backend endpoint for AI Copilot queries.
    
    Validates user permissions before processing.
    Logs all requests for audit purposes.
    """
    try:
        data = json.loads(request.body)
        user_query = data.get('query', '').strip()

        # Rate limit per user before processing
        allowed_rl, retry_after = _check_rate_limit(request.user)
        if not allowed_rl:
            AuditLog.objects.create(
                user=request.user,
                action='AI_QUERY_RATE_LIMITED',
                object_type='AIQuery',
                object_id='',
                details={
                    'query': user_query[:100],
                    'retry_after': retry_after,
                    'limit': RATE_LIMIT_PER_MIN,
                },
                ip_address=get_client_ip(request),
                severity='WARNING',
            )
            _increment_usage_metrics(request.user, allowed=False)
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
            AuditLog.objects.create(
                user=request.user,
                action='AI_QUERY_DENIED',
                object_type='AIQuery',
                object_id='',
                details={
                    'query': user_query[:100],  # Store first 100 chars
                    'reason': denial_reason,
                },
                ip_address=get_client_ip(request),
                severity='WARNING',
            )
            
            _increment_usage_metrics(request.user, allowed=False)
            return JsonResponse({
                'success': False,
                'error': denial_reason
            }, status=403)
        
        # Log successful query
        AuditLog.objects.create(
            user=request.user,
            action='AI_QUERY_SUBMITTED',
            object_type='AIQuery',
            object_id='',
            details={
                'query': user_query[:100],
                'role': getattr(request.user, 'role', 'USER'),
            },
            ip_address=get_client_ip(request),
            severity='INFO',
        )
        
        # Build contextual prompt and call Gemini if configured
        permissions = get_ai_permissions(request.user)
        prompt = build_contextual_prompt(request.user, user_query)

        response_text = None
        api_key = os.environ.get('GEMINI_API_KEY', '')
        if api_key:
            try:
                url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}'
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 500,
                    },
                    "safetySettings": [
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
                    ]
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    # Safely extract text
                    response_text = (
                        data.get('candidates', [{}])[0]
                            .get('content', {})
                            .get('parts', [{}])[0]
                            .get('text')
                    ) or "I'm here to help."
            except urllib.error.HTTPError as e:
                logger.error(f'Gemini HTTPError: {e.code} {e.reason}', exc_info=True)
            except Exception as e:
                logger.error(f'Gemini request failed: {str(e)}', exc_info=True)

        if not response_text:
            # Fallback response if API key missing or error occurred
            response_text = (
                f"I understand you're asking about: {user_query}. "
                f"Your role is {permissions.get('scope', 'general')}. "
                f"For AI-powered answers, ensure GEMINI_API_KEY is configured."
            )

        _increment_usage_metrics(request.user, allowed=True)
        cache.set('ai_copilot_last_success_ts', time.time(), None)
        return JsonResponse({
            'success': True,
            'allowed': True,
            'permissions': permissions,
            'user_role': getattr(request.user, 'role', 'USER'),
            'response': response_text,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body.'
        }, status=400)
    except Exception as e:
        logger.error(f'AI Copilot error: {str(e)}', exc_info=True)
        try:
            cache.incr('ai_copilot_usage_errors_total')
        except ValueError:
            cache.set('ai_copilot_usage_errors_total', 1, None)
        cache.set('ai_copilot_last_error_ts', time.time(), None)
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


@login_required(login_url='/authentication/login/')
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
@login_required(login_url='/authentication/login/')
def ai_copilot_limits(request):
    """Return current rate limit status for the logged-in user."""
    key = f"ai_rl:{getattr(request.user, 'id', 'anon')}"
    now = time.time()
    events = cache.get(key, [])
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
@login_required(login_url='/authentication/login/')
def ai_copilot_config(request):
    """Return AI Copilot backend config visibility for frontend widgets."""
    api_key = os.environ.get('GEMINI_API_KEY', '')
    enabled = bool(api_key)
    model = 'gemini-pro' if enabled else None
    return JsonResponse({
        'success': True,
        'enabled': enabled,
        'model': model,
        'rate_limit': RATE_LIMIT_PER_MIN,
        'window_seconds': RATE_LIMIT_WINDOW,
        'user_role': getattr(request.user, 'role', 'USER'),
    })


@require_GET
@login_required(login_url='/authentication/login/')
def ai_copilot_audit_feed(request):
    """Return recent AI-related audit logs; staff/admin only."""
    user = request.user
    if not (user.is_staff or user.is_superuser or getattr(user, 'role', '') in ('ADMIN', 'LEADERSHIP')):
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
    role = getattr(user, 'role', 'USER')
    context = "You are an AI assistant for a school management system. "

    if role in ['ADMIN', 'LEADERSHIP']:
        context += (
            f"The user is an administrator named {user_name}. "
            "Help with system analytics, user management, financial summaries, compliance tasks, and administrative operations. "
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
