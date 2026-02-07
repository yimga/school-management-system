import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.functional import cached_property

from .permissions import can_access_module
from .utils import get_user_role

logger = logging.getLogger(__name__)


class RoleBasedSessionTimeoutMiddleware:
    """
    Adjust session expiry based on the authenticated user's role so
    sensitive dashboards time out faster than less privileged ones.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.role_timeouts = getattr(settings, "ROLE_SESSION_TIMEOUTS", {})

    def __call__(self, request):
        self.apply_timeout(request)
        return self.get_response(request)

    def apply_timeout(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return

        timeout = self.role_timeouts.get(user.role, settings.SESSION_COOKIE_AGE)
        request.session.set_expiry(timeout)


class ModuleAccessMiddleware:
    """
    Enforce module-level access rules for all authenticated users.
    Uses module namespace + HTTP method to determine read/write access.
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    BYPASS_PREFIXES = (
        "/static/",
        "/media/",
        "/assets/",
        "/favicon.ico",
        "/.well-known/",
        "/health/",
        "/healthz/",
        "/metrics/",
    )
    BYPASS_PATHS = {
        "/authentication/login/",
        "/authentication/logout/",
        "/authentication/redirect/",
        "/authentication/backend/",
        "/admin/login/",
        "/admin/logout/",
        "/api/schema/",
        "/api/schema/ui/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        if self._is_bypass_path(path):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        module = self._resolve_module(request, path)
        if not module:
            # Fail-closed: if path looks like a module path but resolution returned None, deny access
            if self._path_looks_module_like(path):
                logger.warning(
                    "Module access denied: path looks module-like but module could not be resolved (path=%r)",
                    path,
                    extra={"path": path},
                )
                if path.startswith("/api/"):
                    return JsonResponse(
                        {"detail": "Module access denied.", "path": path},
                        status=403,
                    )
                if self._accepts_html(request):
                    return render(
                        request,
                        "requests/access_denied.html",
                        {"module": None, "action": "read", "next": path},
                        status=403,
                    )
                return HttpResponseForbidden("Module access denied.")
            return self.get_response(request)

        # Allow authenticated users to submit module access requests
        if module == "requests" and request.resolver_match:
            if request.resolver_match.view_name == "requests:module_access":
                return self.get_response(request)

        # Allow guardians to POST to finance request-access URLs without full finance module access
        if module == "finance" and request.resolver_match:
            view_name = request.resolver_match.view_name
            if view_name in ("finance:invoice_request_access", "finance:finance_request_access"):
                return self.get_response(request)

        action = "read" if request.method in self.SAFE_METHODS else "write"
        if can_access_module(user, module, action=action):
            return self.get_response(request)

        # For /api/ paths return JSON so API clients get machine-readable errors
        if path.startswith("/api/"):
            return JsonResponse(
                {"detail": "You do not have access to this module.", "module": module, "action": action},
                status=403,
            )
        # Block with a friendly request-access page for HTML requests
        if self._accepts_html(request):
            return render(
                request,
                "requests/access_denied.html",
                {
                    "module": module,
                    "action": action,
                    "next": path,
                },
                status=403,
            )

        return HttpResponseForbidden("You do not have access to this module.")

    def _accepts_html(self, request) -> bool:
        path = (getattr(request, "path", "") or "")
        # API clients often send Accept: */*; treat as JSON for /api/ so they get JSON error responses
        if path.startswith("/api/"):
            accept = request.headers.get("Accept", "")
            return "text/html" in accept and "*/*" not in (accept or "").split(",")[0].strip()
        accept = request.headers.get("Accept", "")
        return "text/html" in accept or "*/*" in accept

    def _is_bypass_path(self, path: str) -> bool:
        if path in self.BYPASS_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in self.BYPASS_PREFIXES)

    # Fallback map for path prefixes when URL has no namespace/app_name (avoids bypassing module RBAC)
    PATH_PREFIX_TO_MODULE = (
        ("/portal/", "portal"),
        ("/evals/", "evals"),
        ("/finance/", "finance"),
        ("/reports/", "reports"),
        ("/people/", "people"),
        ("/analytics/", "analytics"),
        ("/payroll/", "payroll"),
        ("/compliance/", "compliance"),
        ("/communication/", "communication"),
        ("/requests/", "requests"),
        ("/academics/", "academics"),
    )
    MODULE_LIKE_FIRST_SEGMENTS = frozenset(
        {"admin", "api", "portal", "evals", "finance", "reports", "people", "analytics", "payroll", "compliance", "communication", "requests", "academics"}
    )

    def _path_looks_module_like(self, path: str) -> bool:
        """True if the first path segment is a known module name (e.g. /portal or /portal/)."""
        segment = (path or "").strip("/").split("/")[0] or ""
        return segment.lower() in self.MODULE_LIKE_FIRST_SEGMENTS

    def _resolve_module(self, request, path: str) -> str | None:
        try:
            match = resolve(path)
        except Exception:
            match = None

        if match:
            request.resolver_match = match
            if match.namespace:
                return match.namespace.lower()
            if match.app_name:
                return match.app_name.lower()

        if path.startswith("/admin/"):
            return "admin"
        if path.startswith("/api/"):
            return "api"
        for prefix, module in self.PATH_PREFIX_TO_MODULE:
            if path.startswith(prefix):
                return module
        return None


class RequireMFAMiddleware:
    """
    Phase 4: When SiteSettings.require_mfa_roles contains the user's role,
    redirect to MFA setup if they have no TOTP device (zero-cost MFA for compliance).
    """
    BYPASS_PREFIXES = ("/static/", "/media/", "/favicon.ico", "/health/", "/healthz/", "/metrics/", "/api/")
    BYPASS_PATHS = (
        "/authentication/login/",
        "/authentication/logout/",
        "/authentication/redirect/",
        "/authentication/backend/",
        "/authentication/claim-invite/",
        "/admin/login/",
        "/admin/logout/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or "").rstrip("/") or "/"
        if any(path.startswith(p) for p in self.BYPASS_PREFIXES) or path in self.BYPASS_PATHS:
            return self.get_response(request)
        # Allow MFA setup and verify so user can complete setup
        if "/mfa/setup" in path or "/mfa/verify" in path:
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        try:
            from apps.siteconfig.models import SiteSettings
            from django_otp import user_has_device
            from django_otp.plugins.otp_totp.models import TOTPDevice

            site = SiteSettings.get_solo()
            require_all_staff = getattr(site, "require_mfa_all_staff", False)
            required_roles = getattr(site, "require_mfa_roles", None) or []

            role = get_user_role(user)
            must_have_mfa = False
            if require_all_staff and user.is_staff:
                must_have_mfa = True
            elif required_roles:
                required_normalized = [
                    r.upper() if isinstance(r, str) else str(r).upper()
                    for r in required_roles
                ]
                if role in required_normalized:
                    must_have_mfa = True

            try:
                has_device = user_has_device(user, confirmed=True)
            except TypeError:
                has_device = user_has_device(user)

            # Ensure only confirmed TOTP devices count as configured MFA
            if not has_device:
                has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()

            # If MFA is required OR user has MFA configured, enforce verification
            if must_have_mfa and not has_device:
                mfa_setup_url = reverse("accounts:mfa_setup")
                if path != mfa_setup_url.rstrip("/") and not path.endswith(mfa_setup_url):
                    return redirect(mfa_setup_url + "?next=" + (request.GET.get("next") or request.path))
                return self.get_response(request)

            if has_device or must_have_mfa:
                if not self._is_mfa_verified(request):
                    mfa_verify_url = reverse("accounts:mfa_verify")
                    if path != mfa_verify_url.rstrip("/") and not path.endswith(mfa_verify_url):
                        return redirect(mfa_verify_url + "?next=" + (request.GET.get("next") or request.path))
        except Exception:
            pass
        return self.get_response(request)

    @staticmethod
    def _is_mfa_verified(request) -> bool:
        if request.session.get("mfa_verified"):
            return True
        until_raw = request.session.get("mfa_verified_until")
        if not until_raw:
            return False
        try:
            until_dt = timezone.datetime.fromisoformat(until_raw)
            if timezone.is_naive(until_dt):
                until_dt = timezone.make_aware(until_dt, timezone.get_current_timezone())
            if timezone.now() <= until_dt:
                return True
        except Exception:
            pass
        # Expired or invalid
        request.session.pop("mfa_verified_until", None)
        return False
        # Allow MFA setup and verify so user can complete setup
        if "/mfa/setup" in path or "/mfa/verify" in path:
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        try:
            from apps.siteconfig.models import SiteSettings
            from django_otp import user_has_device

            site = SiteSettings.get_solo()
            require_all_staff = getattr(site, "require_mfa_all_staff", False)
            required_roles = getattr(site, "require_mfa_roles", None) or []

            must_have_mfa = False
            if require_all_staff and user.is_staff:
                must_have_mfa = True
            elif required_roles:
                role = get_user_role(user)
                if role in [r.upper() if isinstance(r, str) else str(r) for r in required_roles]:
                    must_have_mfa = True

            if not must_have_mfa or user_has_device(user):
                return self.get_response(request)
            # Staff must set up MFA → redirect to setup
            mfa_setup_url = reverse("accounts:mfa_setup")
            if path != mfa_setup_url.rstrip("/") and not path.endswith(mfa_setup_url):
                return redirect(mfa_setup_url + "?next=" + (request.GET.get("next") or request.path))
        except Exception:
            pass
        return self.get_response(request)
