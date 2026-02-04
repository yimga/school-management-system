from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.utils.functional import cached_property

from .permissions import can_access_module
from .utils import get_user_role


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
    BYPASS_PREFIXES = ("/static/", "/media/", "/favicon.ico", "/health/", "/healthz/", "/metrics/")
    BYPASS_PATHS = (
        "/authentication/login/",
        "/authentication/logout/",
        "/authentication/redirect/",
        "/authentication/backend/",
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
            site = SiteSettings.get_solo()
            required_roles = getattr(site, "require_mfa_roles", None) or []
            if not required_roles:
                return self.get_response(request)
            role = get_user_role(user)
            if role not in [r.upper() if isinstance(r, str) else str(r) for r in required_roles]:
                return self.get_response(request)
            from django_otp import user_has_device
            if user_has_device(user):
                return self.get_response(request)
            # Role requires MFA but user has no TOTP device → redirect to setup
            mfa_setup_url = reverse("accounts:mfa_setup")
            if path != mfa_setup_url.rstrip("/") and not path.endswith(mfa_setup_url):
                return redirect(mfa_setup_url + "?next=" + (request.GET.get("next") or request.path))
        except Exception:
            pass
        return self.get_response(request)

