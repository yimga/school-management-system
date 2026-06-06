"""
Phase 4: Access Control & Audit Logging Middleware

Tracks all HTTP requests, logs failed access attempts, and enriches
audit context with request metadata (IP address, user agent, etc.).
Phase 6: IP/Country-based access control enforcement.
§2.4: Typed exception tuples and structured logging (no broad except).
"""

import logging
from time import time

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, connection, transaction
from django.db.transaction import TransactionManagementError
from django.db.utils import IntegrityError, OperationalError
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from apps.compliance.access_control import check_request_access
from apps.compliance.models_audit import AccessLog, AuditLog
from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    log_view_exception,
)

logger = logging.getLogger(__name__)


def _access_log_middleware_writes_enabled() -> bool:
    """Skip per-request AccessLog INSERTs during tests unless explicitly opted in."""
    return bool(
        getattr(settings, "COMPLIANCE_AUDIT_ACCESS_LOG_MIDDLEWARE_WRITES", True)
    )


def _should_persist_access_log(request, response) -> bool:
    """Sample successful GET/HEAD traffic; always log mutations and errors."""
    method = (getattr(request, "method", "") or "GET").upper()
    if method not in {"GET", "HEAD", "OPTIONS"}:
        return True
    if getattr(response, "status_code", 200) >= 400:
        return True
    rate = float(getattr(settings, "COMPLIANCE_ACCESS_LOG_GET_SAMPLE_RATE", 1.0))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    import random

    return random.random() < rate


# §2.4: Typed tuples for compliance middleware (allowlist 0).
_RESET_DB_STATE_ERRORS = (
    TransactionManagementError,
    OperationalError,
    DatabaseError,
    AttributeError,
    TypeError,
)
_AUDIT_EXTRACT_ERROR_RESPONSE_ERRORS = (
    UnicodeDecodeError,
    AttributeError,
    TypeError,
    ValueError,
)
_AUDIT_MIDDLEWARE_LOG_ACCESS_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    KeyError,
    DatabaseError,
    IntegrityError,
)
_ACCESS_CHECK_RUNTIME_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    RuntimeError,
    ObjectDoesNotExist,
    DatabaseError,
    OperationalError,
)
_LOG_ACCESS_DENIAL_ERRORS = (
    DatabaseError,
    TransactionManagementError,
    ObjectDoesNotExist,
    AttributeError,
    TypeError,
    ValueError,
)
_COMPLIANCE_GUARD_CHECK_ERRORS = (
    ObjectDoesNotExist,
    DatabaseError,
    OperationalError,
    AttributeError,
    TypeError,
    ImportError,
)


def _reset_db_state() -> None:
    """Reset a broken transaction after a handled DB error."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        elif connection.needs_rollback:
            connection.rollback()
    except _RESET_DB_STATE_ERRORS:
        pass


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all HTTP requests to AccessLog for audit trail.
    Captures: user, IP address, method, path, status, response time.
    """

    # Paths to skip from access logging (noisy, non-user actions)
    SKIP_PATHS = {
        "/static/",
        "/media/",
        "/assets/",
        "/favicon.ico",
        "/.well-known/",
        "/health/",
        "/healthz/",
        "/ready",
        "/api/health/",
        "/status/",
    }
    SKIP_EXACT_PATHS = {
        "/",
    }

    def process_request(self, request):
        """Store start time for response time calculation."""
        request._start_time = time()
        return None

    def process_response(self, request, response):
        """Log the HTTP request/response to AccessLog."""
        if not _access_log_middleware_writes_enabled():
            return response
        try:
            if connection.needs_rollback:
                _reset_db_state()
                return response
            # Skip logging for static/media/health paths
            path = request.path or "/"
            if path in self.SKIP_EXACT_PATHS:
                return response
            if any(path.startswith(skip) for skip in self.SKIP_PATHS):
                return response

            if not _should_persist_access_log(request, response):
                return response

            # Calculate response time
            start_time = getattr(request, "_start_time", None)
            response_time_ms = None
            if start_time:
                response_time_ms = int((time() - start_time) * 1000)

            # Determine access type
            access_type = self._get_access_type(request)

            # Extract error message if status >= 400
            error_message = ""
            if response.status_code >= 400:
                try:
                    error_message = self._extract_error(response) or ""
                except _AUDIT_EXTRACT_ERROR_RESPONSE_ERRORS:
                    error_message = ""

            # Get user
            user = None
            if hasattr(request, "user") and request.user.is_authenticated:
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
                error_message=error_message or "",  # Ensure never None
            )
        except ValueError as e:
            # e.g. database router prevents user FK assignment (multi-DB)
            logger.debug("AccessLog skipped (router/relation): %s", e)
        except (DatabaseError, TransactionManagementError) as e:
            _reset_db_state()
            log_view_exception(request, "Failed to log access", extra={"error": str(e)})
            # Avoid traceback spam when table is missing (e.g. migrations not run yet)
            if isinstance(e, OperationalError) and (
                "no such table" in str(e).lower() or "does not exist" in str(e).lower()
            ):
                logger.warning(
                    "Failed to log access (table missing? run migrate): %s", e
                )
            else:
                logger.warning("Failed to log access: %s", e, exc_info=True)
        except _AUDIT_MIDDLEWARE_LOG_ACCESS_ERRORS as e:
            log_view_exception(request, "Failed to log access", extra={"error": str(e)})

        return response

    def process_exception(self, request, exception):
        """Log exceptions/failed requests."""
        if not _access_log_middleware_writes_enabled():
            return None
        try:
            from apps.platform_runtime.transient_db import is_transient_database_error

            if is_transient_database_error(exception):
                _reset_db_state()
                return None
            if connection.needs_rollback:
                _reset_db_state()
                return None
            path = request.path or "/"
            if path in self.SKIP_EXACT_PATHS:
                return None
            if any(path.startswith(skip) for skip in self.SKIP_PATHS):
                return None
            user = None
            if hasattr(request, "user") and request.user.is_authenticated:
                user = request.user

            ip_address = self._get_ip_address(request)

            AccessLog.objects.create(
                user=user,
                access_type=self._get_access_type(request),
                resource=request.path,
                request_method=request.method,
                status=500,
                ip_address=ip_address,
                error_message=str(exception)[:500],
            )
        except ValueError as e:
            logger.debug("AccessLog exception skipped (router/relation): %s", e)
        except (DatabaseError, TransactionManagementError) as e:
            _reset_db_state()
            log_view_exception(
                request, "Failed to log exception", extra={"error": str(e)}
            )
            if isinstance(e, OperationalError) and (
                "no such table" in str(e).lower() or "does not exist" in str(e).lower()
            ):
                logger.warning(
                    "Failed to log exception (table missing? run migrate): %s", e
                )
            else:
                logger.warning("Failed to log exception: %s", e, exc_info=True)
        except _AUDIT_MIDDLEWARE_LOG_ACCESS_ERRORS as e:
            log_view_exception(
                request, "Failed to log exception", extra={"error": str(e)}
            )

        return None  # Re-raise the exception

    @staticmethod
    def _get_access_type(request):
        """Determine access type (WEB, API, DOWNLOAD, etc.)."""
        path = request.path

        if path.startswith("/api/"):
            return AccessLog.AccessType.API
        elif "download" in path or "export" in path:
            return AccessLog.AccessType.DOWNLOAD
        elif path.startswith("/admin/"):
            return AccessLog.AccessType.ADMIN
        else:
            return AccessLog.AccessType.WEB

    @staticmethod
    def _get_ip_address(request):
        """Extract real IP address from request (handles proxies)."""
        # Check for IP through proxy headers
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "")
        return ip[:45]

    @staticmethod
    def _extract_error(response):
        """Extract error message from response."""
        try:
            if hasattr(response, "content"):
                content = response.content.decode("utf-8", errors="ignore")
                # Try to find error message in common patterns
                if "error" in content.lower():
                    # Very basic extraction - just take first 500 chars
                    return content[:500]
        except _AUDIT_EXTRACT_ERROR_RESPONSE_ERRORS:
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
        getattr(request, "user", None)

        # Attach user info for decorators to use
        request.user_ip = self._get_ip_address(request)
        request.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
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
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "")
        return ip[:45]


class IPCountryAccessMiddleware(MiddlewareMixin):
    """
    Enforce IP and country-based access control rules.
    Blocks requests from denied IPs/countries before they reach views.
    """

    # Paths to bypass access control (e.g., health checks, auth/bootstrap routes, static files)
    # Keep this list strict: these routes either have their own auth guards or must stay probe-safe.
    BYPASS_PATH_PREFIXES = {
        "/static/",
        "/media/",
        "/assets/",
        "/favicon.ico",
        "/.well-known/",
        "/health/",
        "/healthz/",
        "/ready",
        "/authentication/",
        "/super/",
        "/offline/",
        "/api/health/",
        "/api/weather/context/",
        "/status/",
        "/admin/jsi18n/",  # Django admin i18n
    }
    BYPASS_EXACT_PATHS = {
        "/",
    }

    def process_request(self, request):
        """Check IP/country access before view execution."""
        path = request.path or "/"

        # Skip bypass paths
        if path in self.BYPASS_EXACT_PATHS:
            return None
        if any(path.startswith(skip) for skip in self.BYPASS_PATH_PREFIXES):
            return None

        # Check if access control is enabled
        if not getattr(settings, "ENABLE_IP_COUNTRY_ACCESS_CONTROL", True):
            return None

        # Bypass for superusers (if configured)
        if getattr(settings, "BYPASS_ACCESS_CONTROL_FOR_SUPERUSERS", True):
            if (
                hasattr(request, "user")
                and request.user.is_authenticated
                and request.user.is_superuser
            ):
                return None

        # Check access
        try:
            is_allowed, reason = check_request_access(request)
        except _ACCESS_CHECK_RUNTIME_ERRORS as exc:
            # Never block requests due to access-control runtime errors.
            log_exception_with_context(
                "IP/country access check failed; allowing request",
                school_id=getattr(getattr(request, "school", None), "id", None),
                extra={"path": request.path, "error": str(exc)},
            )
            return None

        if not is_allowed:
            if not _access_log_middleware_writes_enabled():
                return HttpResponseForbidden(
                    f"<h1>Access Denied</h1><p>{reason}</p>"
                    "<p>If you believe this is an error, contact support.</p>"
                )
            # Log the blocked attempt (skip if AccessLog table missing)
            user = (
                request.user
                if hasattr(request, "user") and request.user.is_authenticated
                else None
            )
            ip_address = self._get_ip_address(request)
            try:
                AccessLog.objects.create(
                    user=user,
                    access_type=AccessLog.AccessType.WEB,
                    resource=request.path,
                    request_method=request.method,
                    status=403,
                    ip_address=ip_address,
                    error_message=f"Access denied: {reason}",
                )
                log_access_denial(
                    user=user,
                    action="HTTP_REQUEST",
                    resource=request.path,
                    reason=f"IP/Country access denied: {reason}",
                    ip_address=ip_address,
                    severity="HIGH",
                )
            except (DatabaseError, OperationalError, TransactionManagementError):
                _reset_db_state()
                logger.debug("Access log skipped (table missing or DB error)")
            except _LOG_ACCESS_DENIAL_ERRORS as e:
                log_exception_with_context(
                    "Failed to log access denial (IP/country block)",
                    school_id=getattr(getattr(request, "school", None), "id", None),
                    extra={"path": request.path, "error": str(e)},
                )

            # Return 403 Forbidden
            return HttpResponseForbidden(
                f"<h1>Access Denied</h1><p>{reason}</p><p>If you believe this is an error, contact support.</p>"
            )

        return None

    @staticmethod
    def _get_ip_address(request):
        """Extract real IP address from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "")
        return ip[:45]


def log_access_denial(user, action, resource, reason, ip_address="", severity="HIGH"):
    """
    Utility function to log failed access attempts.
    Called by access control decorators when permission is denied.
    """
    try:
        AuditLog.objects.create(
            action=AuditLog.Action.ACCESS_DENIED,
            model_name="ACCESS_CONTROL",
            object_id=resource,
            object_repr=f"Denied: {action}",
            app_label="compliance",
            old_values={"requested_action": action},
            new_values={},
            reason=reason,
            sensitivity=severity,
            ip_address=ip_address,
        )
    except _LOG_ACCESS_DENIAL_ERRORS as e:
        log_exception_with_context(
            "log_access_denial: failed to create AuditLog",
            school_id=None,
            extra={"action": action, "resource": resource[:200], "error": str(e)},
        )


# ---------------------------------------------------------------------------
# Phase Compliance (plan 3.9): Region → feature_code → status guard
# ---------------------------------------------------------------------------

COMPLIANCE_GUARD_PATH_MAP = {
    # Path prefix -> feature_code checked against RegionFeatureCompliance
    # GDPR/DSAR execution and export
    "/compliance/gdpr/export/": "Export_All_Student_Data",
    "/compliance/gdpr/erasure-request/": "Right_to_Erasure",
    # Public admissions capture (regional privacy policy toggle)
    "/api/admissions/lead/": "Lead_Capture_API",
    # Interoperability controls
    "/api/interop/oneroster/": "OneRoster_Interop",
    "/api/interop/lti13/": "LTI13_Interop",
    "/api/oneroster/v1p1/": "OneRoster_Interop",
    "/api/scim/v2/": "SCIM_Provisioning",
    "/lti/launch/": "LTI13_Interop",
    "/lti/jwks.json": "LTI13_Interop",
}


class ComplianceGuardMiddleware(MiddlewareMixin):
    """
    After TenantMiddleware. For request.school.default_region, load RegionFeatureCompliance.
    If path matches COMPLIANCE_GUARD_PATH_MAP and rule status is DISABLED/RESTRICTED, return 403.
    """

    def process_request(self, request):
        school = getattr(request, "school", None)
        if not school:
            return None
        path = (request.path or "").strip()
        for prefix, feature_code in COMPLIANCE_GUARD_PATH_MAP.items():
            if not feature_code:
                continue
            if (
                path == prefix
                or path.startswith(prefix.rstrip("/") + "/")
                or path == prefix.rstrip("/")
            ):
                if self._is_blocked(school, feature_code):
                    return self._block_response(request, feature_code)
                break
        return None

    def _is_blocked(self, school, feature_code):
        region_id = getattr(school, "default_region_id", None)
        if not region_id:
            return False
        try:
            from apps.compliance.models import RegionFeatureCompliance

            rule = RegionFeatureCompliance.objects.filter(
                region_id=region_id,
                feature_code=feature_code,
            ).first()
            if not rule:
                return False
            return rule.status in (
                RegionFeatureCompliance.Status.DISABLED,
                RegionFeatureCompliance.Status.RESTRICTED,
            )
        except _COMPLIANCE_GUARD_CHECK_ERRORS as e:
            logger.debug("ComplianceGuard check failed: %s", e)
            return False

    def _block_response(self, request, feature_code):
        if (
            request.path.startswith("/api/")
            or (request.headers.get("Accept") or "").find("application/json") >= 0
        ):
            return JsonResponse(
                {
                    "error": "compliance_restricted",
                    "feature": feature_code,
                    "detail": "This action is not permitted for your region (compliance policy).",
                },
                status=403,
            )
        return HttpResponseForbidden(
            f"<h1>403 Forbidden</h1><p>This action ({feature_code}) is not permitted for your region (compliance policy).</p>"
        )
