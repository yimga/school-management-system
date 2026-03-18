import logging
from http.cookies import SimpleCookie

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404
from django.utils import timezone

from apps.schools.host_routing import public_host_kind
from apps.schools.tenant_url import build_manager_absolute_url
from apps.platform_runtime.helpers import get_effective_site_settings

from .permissions import can_access_module
from .utils import get_user_role

logger = logging.getLogger(__name__)


class ManagerCookieIsolationMiddleware:
    """
    Keep manager-host auth isolated from tenant/base auth by aliasing manager-specific
    cookie names to Django's default names on request and rewriting them on response.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.session_cookie_name = settings.SESSION_COOKIE_NAME
        self.csrf_cookie_name = settings.CSRF_COOKIE_NAME
        self.manager_session_cookie_name = getattr(
            settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid"
        )
        self.manager_csrf_cookie_name = getattr(
            settings, "MANAGER_CSRF_COOKIE_NAME", "rmc_manager_csrftoken"
        )
        self.manager_session_cookie_domain = getattr(
            settings, "MANAGER_SESSION_COOKIE_DOMAIN", None
        )
        self.manager_csrf_cookie_domain = getattr(
            settings, "MANAGER_CSRF_COOKIE_DOMAIN", None
        )

    def __call__(self, request):
        self._alias_request_cookies(request)
        response = self.get_response(request)
        return self._rewrite_response_cookies(request, response)

    def _is_manager_request(self, request) -> bool:
        host = (
            (request.META.get("HTTP_HOST") or request.META.get("SERVER_NAME") or "")
            .strip()
            .lower()
        )
        return public_host_kind(host) == "manager"

    def _alias_request_cookies(self, request):
        if not self._is_manager_request(request):
            return
        raw_cookie = request.META.get("HTTP_COOKIE", "")
        if not raw_cookie:
            return
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        changed = False
        for manager_name, default_name in (
            (self.manager_session_cookie_name, self.session_cookie_name),
            (self.manager_csrf_cookie_name, self.csrf_cookie_name),
        ):
            default_morsel = cookie.get(default_name)
            default_blank = (
                default_morsel is None or str(default_morsel.value or "").strip() == ""
            )
            if manager_name in cookie and default_blank:
                cookie[default_name] = cookie[manager_name].value
                changed = True
        if not changed:
            return
        request.META["HTTP_COOKIE"] = "; ".join(
            f"{key}={morsel.value}" for key, morsel in cookie.items()
        )
        request.COOKIES = {key: morsel.value for key, morsel in cookie.items()}

    def _rewrite_response_cookies(self, request, response):
        if not self._is_manager_request(request):
            return response
        self._mirror_cookie(
            response,
            source_name=self.session_cookie_name,
            target_name=self.manager_session_cookie_name,
            target_domain=self.manager_session_cookie_domain,
            source_domain=getattr(settings, "SESSION_COOKIE_DOMAIN", None),
        )
        self._mirror_cookie(
            response,
            source_name=self.csrf_cookie_name,
            target_name=self.manager_csrf_cookie_name,
            target_domain=self.manager_csrf_cookie_domain,
            source_domain=getattr(settings, "CSRF_COOKIE_DOMAIN", None),
        )
        return response

    def _mirror_cookie(
        self,
        response,
        *,
        source_name: str,
        target_name: str,
        target_domain,
        source_domain,
    ):
        morsel = response.cookies.get(source_name)
        if morsel is None:
            return
        path = morsel["path"] or "/"
        samesite = morsel["samesite"] or None
        secure = bool(morsel["secure"])
        httponly = bool(morsel["httponly"])
        delete_cookie = self._morsel_is_delete(morsel)
        if delete_cookie:
            response.delete_cookie(
                target_name, path=path, domain=target_domain, samesite=samesite
            )
        else:
            response.set_cookie(
                target_name,
                morsel.value,
                max_age=self._parse_int(morsel["max-age"]),
                expires=morsel["expires"] or None,
                path=path,
                domain=target_domain,
                secure=secure,
                httponly=httponly,
                samesite=samesite,
            )
        response.delete_cookie(
            source_name, path=path, domain=source_domain, samesite=samesite
        )

    @staticmethod
    def _parse_int(value):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _morsel_is_delete(morsel) -> bool:
        max_age = str(morsel["max-age"] or "").strip()
        expires = str(morsel["expires"] or "").lower()
        return morsel.value == "" and (max_age == "0" or "1970" in expires)


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
        "/ready",
        "/status/",
        "/metrics/",
        "/siteconfig/preferences",  # Any authenticated user can manage own preferences (theme, dashboard, etc.)
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
        if getattr(request, "public_host_kind", None) == "manager":
            return self.get_response(request)
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
            if view_name in (
                "finance:invoice_request_access",
                "finance:finance_request_access",
            ):
                return self.get_response(request)

        action = "read" if request.method in self.SAFE_METHODS else "write"
        if can_access_module(user, module, action=action):
            return self.get_response(request)

        # For /api/ paths return JSON so API clients get machine-readable errors
        if path.startswith("/api/"):
            return JsonResponse(
                {
                    "detail": "You do not have access to this module.",
                    "module": module,
                    "action": action,
                },
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
        path = getattr(request, "path", "") or ""
        # API clients often send Accept: */*; treat as JSON for /api/ so they get JSON error responses
        if path.startswith("/api/"):
            accept = request.headers.get("Accept", "")
            return (
                "text/html" in accept
                and "*/*" not in (accept or "").split(",")[0].strip()
            )
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
        {
            "admin",
            "api",
            "portal",
            "evals",
            "finance",
            "reports",
            "people",
            "analytics",
            "payroll",
            "compliance",
            "communication",
            "requests",
            "academics",
        }
    )

    def _path_looks_module_like(self, path: str) -> bool:
        """True if the first path segment is a known module name (e.g. /portal or /portal/)."""
        segment = (path or "").strip("/").split("/")[0] or ""
        return segment.lower() in self.MODULE_LIKE_FIRST_SEGMENTS

    def _resolve_module(self, request, path: str) -> str | None:
        try:
            match = resolve(path)
        except Resolver404:
            match = None

        if match:
            request.resolver_match = match
            if match.namespace:
                namespace = match.namespace.lower()
                if namespace in {"api_v1", "api-v1"}:
                    return "api"
                return namespace
            if match.app_name:
                app_name = match.app_name.lower()
                if app_name in {"api_v1", "api-v1"}:
                    return "api"
                return app_name

        if path.startswith("/admin/"):
            return "admin"
        if path.startswith("/api/"):
            return "api"
        for prefix, module in self.PATH_PREFIX_TO_MODULE:
            if path.startswith(prefix):
                return module
        return None


class TenantHostControlPlaneIsolationMiddleware:
    """
    Platform operators must enter tenant hosts through the signed impersonation flow,
    not through normal tenant RBAC. This closes scattered SUPERADMIN allow-lists in
    legacy tenant views without requiring every view to know control-plane semantics.
    """

    ALLOWED_TENANT_PATHS = {
        "/authentication/impersonate/",
        "/authentication/end-impersonation/",
        "/authentication/logout/",
    }
    ALLOWED_TENANT_PREFIXES = (
        "/static/",
        "/media/",
        "/assets/",
        "/favicon.ico",
        "/health/",
        "/healthz/",
        "/ready",
        "/status/",
        "/metrics/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "public_host_kind", None) != "tenant":
            return self.get_response(request)

        path = request.path or "/"
        if path in self.ALLOWED_TENANT_PATHS or any(
            path.startswith(prefix) for prefix in self.ALLOWED_TENANT_PREFIXES
        ):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if (
            not user
            or not user.is_authenticated
            or getattr(user, "is_superuser", False)
        ):
            return self.get_response(request)

        role = (getattr(user, "role", "") or "").upper()
        if role != "SUPERADMIN":
            return self.get_response(request)

        impersonation = request.session.get("impersonation") or {}
        school = getattr(request, "school", None)
        if school and str(impersonation.get("school_id") or "") == str(school.id):
            return self.get_response(request)

        return redirect(build_manager_absolute_url(request, "/super/"))


class RequireMFAMiddleware:
    """
    Phase 4: When SiteSettings.require_mfa_roles contains the user's role,
    redirect to MFA setup if they have no TOTP device (zero-cost MFA for compliance).
    """

    BYPASS_PREFIXES = (
        "/static/",
        "/media/",
        "/favicon.ico",
        "/health/",
        "/healthz/",
        "/ready",
        "/status/",
        "/metrics/",
        "/api/",
    )
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
        if (
            any(path.startswith(p) for p in self.BYPASS_PREFIXES)
            or path in self.BYPASS_PATHS
        ):
            return self.get_response(request)
        # Allow MFA setup, verify, and passkey endpoints so user can complete setup
        if "/mfa/setup" in path or "/mfa/verify" in path or "/mfa/passkey/" in path:
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        try:
            from django_otp import user_has_device
            from django_otp.plugins.otp_totp.models import TOTPDevice

            site = get_effective_site_settings(request=request)
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
                has_device = TOTPDevice.objects.filter(
                    user=user, confirmed=True
                ).exists()
            # WebAuthn/Passkey also counts as MFA (25.5, 29.1)
            if not has_device:
                from apps.accounts.models import UserPasskey

                has_device = UserPasskey.objects.filter(user=user).exists()

            # If MFA is required OR user has MFA configured, enforce verification
            if must_have_mfa and not has_device:
                mfa_setup_url = reverse("accounts:mfa_setup")
                if path != mfa_setup_url.rstrip("/") and not path.endswith(
                    mfa_setup_url
                ):
                    return redirect(
                        mfa_setup_url
                        + "?next="
                        + (request.GET.get("next") or request.path)
                    )
                return self.get_response(request)

            if has_device or must_have_mfa:
                if not self._is_mfa_verified(request):
                    mfa_verify_url = reverse("accounts:mfa_verify")
                    if path != mfa_verify_url.rstrip("/") and not path.endswith(
                        mfa_verify_url
                    ):
                        return redirect(
                            mfa_verify_url
                            + "?next="
                            + (request.GET.get("next") or request.path)
                        )
        except (ImportError, AttributeError, TypeError, ValueError):
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
                until_dt = timezone.make_aware(
                    until_dt, timezone.get_current_timezone()
                )
            if timezone.now() <= until_dt:
                return True
        except (ValueError, TypeError, AttributeError):
            pass
        # Expired or invalid
        request.session.pop("mfa_verified_until", None)
        return False


class ImpossibleTravelMiddleware:
    """
    World Engine: single trigger point for impossible-travel check after login.
    Login view sets request._post_login_user = user; this middleware runs in
    process_response and calls check_impossible_travel(request, user).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "_post_login_user", None)
        if user is not None:
            try:
                del request._post_login_user
            except AttributeError:
                pass
            try:
                from apps.accounts.security_audit import check_impossible_travel

                check_impossible_travel(request, user)
            except (ValueError, TypeError, ImportError, AttributeError, OSError) as e:
                logger.exception(
                    "ImpossibleTravelMiddleware: check_impossible_travel failed: %s", e
                )
        return response
