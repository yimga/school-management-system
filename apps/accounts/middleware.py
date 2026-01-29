from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import resolve
from django.utils.functional import cached_property

from .permissions import can_access_module


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

        action = "read" if request.method in self.SAFE_METHODS else "write"
        if can_access_module(user, module, action=action):
            return self.get_response(request)

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
        accept = request.headers.get("Accept", "")
        return "text/html" in accept or "*/*" in accept

    def _is_bypass_path(self, path: str) -> bool:
        if path in self.BYPASS_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in self.BYPASS_PREFIXES)

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
        return None

