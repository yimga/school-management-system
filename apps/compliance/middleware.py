"""
Phase 4: Access Control & Audit Logging Middleware

Tracks all HTTP requests, logs failed access attempts, and enriches
audit context with request metadata (IP address, user agent, etc.).
"""

import logging
from time import time
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from apps.compliance.models_audit import AccessLog, AuditLog

logger = logging.getLogger(__name__)


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all HTTP requests to AccessLog for audit trail.
    Captures: user, IP address, method, path, status, response time.
    """

    # Paths to skip from access logging (noisy, non-user actions)
    SKIP_PATHS = {
        '/static/',
        '/media/',
        '/assets/',
        '/favicon.ico',
        '/.well-known/',
        '/health/',
        '/status/',
    }

    def process_request(self, request):
        """Store start time for response time calculation."""
        request._start_time = time()
        return None

    def process_response(self, request, response):
        """Log the HTTP request/response to AccessLog."""
        try:
            # Skip logging for static/media/health paths
            if any(request.path.startswith(skip) for skip in self.SKIP_PATHS):
                return response

            # Calculate response time
            start_time = getattr(request, '_start_time', None)
            response_time_ms = None
            if start_time:
                response_time_ms = int((time() - start_time) * 1000)

            # Determine access type
            access_type = self._get_access_type(request)

            # Extract error message if status >= 400
            error_message = None
            if response.status_code >= 400:
                try:
                    error_message = self._extract_error(response)
                except Exception:
                    pass

            # Get user
            user = None
            if hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
            
            # Get IP address
            ip_address = self._get_ip_address(request)

            # Log the access
            AccessLog.objects.create(
                user=user,
                access_type=access_type,
                resource=request.path,
                request_method=request.method,
                status=response.status_code,
                response_time_ms=response_time_ms,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                error_message=error_message,
            )
        except Exception as e:
            logger.warning(f"Failed to log access: {e}", exc_info=True)

        return response

    def process_exception(self, request, exception):
        """Log exceptions/failed requests."""
        try:
            user = None
            if hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user

            ip_address = self._get_ip_address(request)

            AccessLog.objects.create(
                user=user,
                access_type=self._get_access_type(request),
                resource=request.path,
                request_method=request.method,
                status=500,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                error_message=str(exception)[:500],
            )
        except Exception as e:
            logger.warning(f"Failed to log exception: {e}", exc_info=True)

        return None  # Re-raise the exception

    @staticmethod
    def _get_access_type(request):
        """Determine access type (WEB, API, DOWNLOAD, etc.)."""
        path = request.path
        
        if path.startswith('/api/'):
            return AccessLog.AccessType.API
        elif 'download' in path or 'export' in path:
            return AccessLog.AccessType.DOWNLOAD
        elif path.startswith('/admin/'):
            return AccessLog.AccessType.ADMIN
        else:
            return AccessLog.AccessType.WEB

    @staticmethod
    def _get_ip_address(request):
        """Extract real IP address from request (handles proxies)."""
        # Check for IP through proxy headers
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip[:45]

    @staticmethod
    def _extract_error(response):
        """Extract error message from response."""
        try:
            if hasattr(response, 'content'):
                content = response.content.decode('utf-8', errors='ignore')
                # Try to find error message in common patterns
                if 'error' in content.lower():
                    # Very basic extraction - just take first 500 chars
                    return content[:500]
        except Exception:
            pass
        return None


class AccessControlMiddleware(MiddlewareMixin):
    """
    Middleware to enforce access control and log permission denials.
    Integrates with role-based access decorators.
    """

    def process_request(self, request):
        """
        Attach access control context to request.
        This enriches decorators with audit information.
        """
        user = getattr(request, 'user', None)
        
        # Attach user info for decorators to use
        request.user_ip = self._get_ip_address(request)
        request.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        request.access_timestamp = timezone.now()

        return None

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Called just before view is executed.
        Can check for access control violations here.
        """
        # Store view info for audit purposes
        request.view_name = f"{view_func.__module__}.{view_func.__name__}"
        return None

    @staticmethod
    def _get_ip_address(request):
        """Extract real IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip[:45]


def log_access_denial(user, action, resource, reason, ip_address='', severity='HIGH'):
    """
    Utility function to log failed access attempts.
    Called by access control decorators when permission is denied.
    """
    try:
        AuditLog.objects.create(
            action=AuditLog.Action.ACCESS_DENIED,
            model_name='ACCESS_CONTROL',
            object_id=resource,
            object_repr=f"Denied: {action}",
            app_label='compliance',
            old_values={'requested_action': action},
            new_values={},
            reason=reason,
            sensitivity=severity,
            ip_address=ip_address,
        )
    except Exception as e:
        logger.warning(f"Failed to log access denial: {e}")
