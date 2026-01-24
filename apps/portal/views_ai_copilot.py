"""
AI Copilot Backend Views - RBAC Protected
Handles AI requests with role-based access control and audit logging.
"""
import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from apps.compliance.models import AuditLog

logger = logging.getLogger(__name__)


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
        
        # Return permissions for frontend to refine response
        permissions = get_ai_permissions(request.user)
        
        return JsonResponse({
            'success': True,
            'allowed': True,
            'permissions': permissions,
            'user_role': getattr(request.user, 'role', 'USER'),
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body.'
        }, status=400)
    except Exception as e:
        logger.error(f'AI Copilot error: {str(e)}', exc_info=True)
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
