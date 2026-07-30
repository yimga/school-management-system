import logging
from http.cookies import CookieError, SimpleCookie

from django.conf import settings
from django.contrib import messages
from django.db import DatabaseError
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404
from django.utils import timezone

from apps.schools.host_routing import public_host_kind
from apps.schools.tenant_url import build_manager_absolute_url
from apps.siteconfig.config_service import get_effective_site_settings

from apps.accounts.effective_access import module_access
from .utils import get_user_role

logger = logging.getLogger(__name__)


class ManagerCookieIsolationMiddleware:
    """
    Keep manager-host auth isolated from tenant/base auth by aliasing manager-specific
    cookie names to Django's default names on request and rewriting them on response.

    On **tenant/base** hosts, when ``sessionid`` is absent but the manager session cookie
    is present (same browser, shared parent domain), copy manager → default names so
    platform operators who logged in on ``manager.*`` stay authenticated when following
    “Open as school” redirects to a school host (impersonation entry requires login).
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
        raw_cookie = request.META.get("HTTP_COOKIE", "")
        if not raw_cookie:
            return
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
        except CookieError:
            return

        if self._is_manager_request(request):
            # Manager host: manager-named cookies → Django default names for SessionMiddleware
            changed = False
            for manager_name, default_name in (
                (self.manager_session_cookie_name, self.session_cookie_name),
                (self.manager_csrf_cookie_name, self.csrf_cookie_name),
            ):
                default_morsel = cookie.get(default_name)
                default_blank = (
                    default_morsel is None
                    or str(default_morsel.value or "").strip() == ""
                )
                if manager_name in cookie and default_blank:
                    cookie[default_name] = cookie[manager_name].value
                    changed = True
            if not changed:
                return
        else:
            # Tenant / base / local: allow session established on manager host to apply here
            # (browser sends rmc_manager_sessionid when domain is shared, e.g. .runmycampus.com).
            changed = False
            for manager_name, default_name in (
                (self.manager_session_cookie_name, self.session_cookie_name),
                (self.manager_csrf_cookie_name, self.csrf_cookie_name),
            ):
                default_morsel = cookie.get(default_name)
                default_blank = (
                    default_morsel is None
                    or str(default_morsel.value or "").strip() == ""
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
        "/authentication/onboarding/",
        "/admin/",
        "/siteconfig/preferences",  # Any authenticated user can manage own preferences (theme, dashboard, etc.)
        "/siteconfig/api/tour-",  # Guided tour + info-tag helpers (all portal roles)
    )
    BYPASS_PATHS = {
        "/authentication/login/",
        "/authentication/logout/",
        "/authentication/redirect/",
        "/authentication/backend/",
        "/admin/",
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
        if module_access(
            user,
            module,
            action=action,
            school=getattr(request, "school", None),
        ):
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
        norm = (path or "").rstrip("/") or "/"
        if norm in {(p or "").rstrip("/") or "/" for p in self.BYPASS_PATHS}:
            return True
        return any(norm.startswith(prefix) for prefix in self.BYPASS_PREFIXES)

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
        ("/feedback/", "feedback"),
        ("/school/feedback/", "feedback"),
        ("/school/roadmap/", "feedback"),
        ("/school/", "portal"),  # Tenant school configuration / setup facade (batch 1192)
        ("/teacher/feedback/", "feedback"),
        ("/parent/feedback/", "feedback"),
        ("/student/feedback/", "feedback"),
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
            "feedback",
            "school",
            "teacher",
            "parent",
            "student",
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
                # Collapse a nested namespace (Django joins them with ":", e.g.
                # "compliance:compliance_reporting") to its TOP-level app namespace, so a
                # sub-section include inherits its parent module's access policy instead of
                # fail-closing on an unregistered colon-joined key (which locked authorized
                # admins out of /compliance/reports/). This seals the whole nested-namespace
                # lockout class, not just the one known case.
                namespace = match.namespace.lower().split(":", 1)[0]
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


def _impersonation_expired(imp) -> bool:
    """True when a session impersonation marker has outlived its dedicated TTL (H7).

    Independent of the ordinary role session timeout: the entry token is short-lived
    (IMPERSONATION_TOKEN_MAX_AGE_SECONDS) but the session marker used to persist until
    explicit exit. Markers written before this change (no ``granted_at``) are not
    force-expired, for backward compatibility."""
    granted = (imp or {}).get("granted_at")
    if not granted:
        return False
    try:
        max_age = int(getattr(settings, "IMPERSONATION_SESSION_MAX_AGE_SECONDS", 3600))  # magic-number-allow: settings-driven-impersonation-ttl-one-hour-fallback
        return (timezone.now().timestamp() - float(granted)) > max_age
    except (TypeError, ValueError):
        return False


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
        # Runs only on real tenant hosts. `public_host_kind` never returns the
        # literal "tenant" (a tenant subdomain resolves to None), so this must key
        # off the positive `is_tenant_host` marker set by UrlConfSwitcherMiddleware
        # — the previous `!= "tenant"` check dead-coded this whole guard.
        if not getattr(request, "is_tenant_host", False):
            return self.get_response(request)

        path = request.path or "/"
        if path in self.ALLOWED_TENANT_PATHS or any(
            path.startswith(prefix) for prefix in self.ALLOWED_TENANT_PREFIXES
        ):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)
        if getattr(user, "is_superuser", False):
            # Break-glass: platform root may browse any tenant host directly. This is
            # the least-observable operator->tenant path, so record it (H6, throttled).
            self._audit_break_glass(request, user)
            return self.get_response(request)

        # Confine EVERY platform operator to the signed impersonation flow — not only the
        # SUPERADMIN role. Lower-tier operator identities (active PlatformOperatorProfile
        # holders, and env-listed operator-role users with no tenant membership) previously
        # slipped past this guard via `role != "SUPERADMIN"` and could browse a tenant host
        # directly, bypassing scope / consent / TTL / read-only / audit. `user_has_control_plane_access`
        # is the same predicate the manager-host guards use, and it returns False for any user
        # holding a SchoolMembership — so a normal tenant user (the overwhelming majority) passes
        # straight through. On an infra/import error we fail OPEN here so a normal tenant user is
        # never trapped; operators remain gated by the manager-host / super-route middleware.
        try:
            from apps.schools.control_plane import user_has_control_plane_access

            if not user_has_control_plane_access(user):
                return self.get_response(request)
        except (ImportError, DatabaseError, AttributeError, TypeError, ValueError):
            return self.get_response(request)

        impersonation = request.session.get("impersonation") or {}
        school = getattr(request, "school", None)
        if (
            school
            and str(impersonation.get("school_id") or "") == str(school.id)
            and not _impersonation_expired(impersonation)
        ):
            return self.get_response(request)

        # No live impersonation (missing, wrong school, or past its dedicated TTL, H7)
        # — a SUPERADMIN-role operator must (re-)enter through the signed flow.
        return redirect(build_manager_absolute_url(request, "/super/"))

    _BREAK_GLASS_AUDIT_THROTTLE_SECONDS = 3600  # magic-number-allow: break-glass-audit-dedupe-window-one-hour

    def _audit_break_glass(self, request, user):
        """Record superuser direct (un-impersonated) tenant-host access.

        Throttled per (user, school) via the cache so a browsing session emits one
        record, not one per request. PII-free (pks only) and best-effort — never
        breaks the request. Skipped when the superuser is actually using the signed
        impersonation flow (already audited at mint)."""
        try:
            school = getattr(request, "school", None)
            if school is None:
                return
            imp = request.session.get("impersonation") or {}
            if str(imp.get("school_id") or "") == str(school.id):
                return
            from django.core.cache import cache

            key = f"break_glass_audit:{getattr(user, 'pk', '?')}:{school.id}"
            if cache.get(key):
                return
            cache.set(key, 1, timeout=self._BREAK_GLASS_AUDIT_THROTTLE_SECONDS)
            logging.getLogger("security.break_glass").warning(
                "break-glass tenant-host access: superuser_pk=%s school_id=%s path=%s",
                getattr(user, "pk", "?"),
                school.id,
                request.path,
            )
        except (AttributeError, TypeError, ValueError, ImportError):
            pass


class ManagerTenantPrimarySurfaceBlockMiddleware:
    """
    Manager host must not expose tenant-primary surfaces that assume ``request.school`` / school workflows:

    - ``/studio/hubs/*`` (workflow, approvals, import)
    - ``/authentication/backend/*`` (school operational backend)

    Operators use signed impersonation on the tenant host instead.

    Defense-in-depth with explicit view guards in ``apps.accounts.views_workflow``.
    """

    _BLOCKED_PREFIXES = (
        "/studio/hubs/",
        "/authentication/backend/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if response is not None:
            return response
        return self.get_response(request)

    def process_request(self, request):
        if (getattr(request, "public_host_kind", None) or "").lower() != "manager":
            return None
        path = request.path or ""
        if not any(path.startswith(p) for p in self._BLOCKED_PREFIXES):
            return None
        if not getattr(request.user, "is_authenticated", False):
            return None
        from django.shortcuts import redirect
        from django.urls import reverse
        from django.utils.translation import gettext as _

        if path.startswith("/authentication/backend/"):
            messages.warning(
                request,
                _(
                    "The school backend runs on the tenant host. "
                    "Use “Open as school” from the super dashboard to impersonate that school."
                ),
            )
        else:
            messages.warning(
                request,
                _(
                    "School workflow hubs (workflow, approvals, import) run on the tenant host. "
                    "Use “Open as school” from the super dashboard to impersonate that school."
                ),
            )
        return redirect(reverse("super:dashboard"))


# Backward-compatible name for imports / older docs
ManagerTenantPrimaryStudioHubBlockMiddleware = ManagerTenantPrimarySurfaceBlockMiddleware


class ImpersonationReadOnlyGuardMiddleware:
    """
    When impersonation is marked read-only, block unsafe HTTP methods on sensitive path prefixes
    so operators cannot mutate tenant data through broad accidental POSTs (admin, APIs, core modules).

    Authentication paths under ``/authentication/`` remain writable so the session can be ended.
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if response is not None:
            return response
        return self.get_response(request)

    def process_request(self, request):
        # Tenant hosts only. Keys off the positive `is_tenant_host` marker
        # (UrlConfSwitcherMiddleware); the previous `!= "tenant"` check never
        # matched a real tenant host and dead-coded the read-only impersonation guard.
        if not getattr(request, "is_tenant_host", False):
            return None
        if request.method in self.SAFE_METHODS:
            return None
        imp = request.session.get("impersonation") or {}
        if not imp:
            return None
        school = getattr(request, "school", None)
        if not school or str(imp.get("school_id") or "") != str(school.id):
            return None
        # Legacy sessions without explicit read_only: do not enforce (backward compatible).
        if "read_only" not in imp:
            return None
        if imp.get("read_only") is not True:
            return None
        path = request.path or ""
        if path.startswith("/authentication/"):
            return None
        if path.startswith("/static/") or path.startswith("/media/"):
            return None
        prefixes = getattr(
            settings,
            "IMPERSONATION_READ_ONLY_BLOCKED_WRITE_PREFIXES",
            (
                "/admin/",
                "/api/",
                "/finance/",
                "/evals/",
                "/people/",
                "/academics/",
                "/communication/",
                "/reports/",
                "/portal/",
                "/studio/",
                "/siteconfig/",
                "/requests/",
                "/payroll/",
                "/analytics/",
                "/compliance/",
            ),
        )
        if any(path.startswith(p) for p in prefixes):
            return HttpResponseForbidden(
                "Read-only impersonation: this write operation is not permitted."
            )
        return None


class RequireMFAMiddleware:
    """
    Phase 4: When require_mfa_roles from effective site settings includes the user's role,
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
        "/ws/wal/",  # WAL HTTP stub returns 401/426 — never MFA HTML redirect
        "/siteconfig/api/tour-",  # Guided tour + info-tag helpers (all portal roles)
        "/authentication/backend/api/operational-health",  # Dashboard health widgets (JSON + SSE)
        "/portal/api/operational-health",  # Parent/teacher portal health widgets (JSON + SSE)
        # First-run owner onboarding: the wizard SETS the password (step 1) and
        # logs the owner in; forcing MFA setup in front of it walls a brand-new,
        # passwordless ADMIN out of their own setup. MFA is offered AFTER the
        # wizard's "done" launchpad routes them to the dashboard.
        "/authentication/onboarding/",
    )
    BYPASS_PATHS = (
        "/authentication/login/",
        "/authentication/logout/",
        "/authentication/redirect/",
        # Do NOT bypass /authentication/backend/ — that let password login soft-skip
        # MFA and land on the dashboard (or bounce to login after a failed handoff).
        "/authentication/claim-invite/",
        "/admin/login/",
        "/admin/logout/",
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self._bypass_paths_normalized = {
            (p or "").rstrip("/") or "/" for p in self.BYPASS_PATHS
        }

    def __call__(self, request):
        path = (request.path or "").rstrip("/") or "/"
        if (
            any(path.startswith(p) for p in self.BYPASS_PREFIXES)
            or path in self._bypass_paths_normalized
        ):
            return self.get_response(request)
        # Allow MFA setup, verify, and passkey endpoints so user can complete setup.
        # Includes the Unified Wizard Engine surface (v4.00.12+): accounts:mfa_setup
        # now 302-redirects to /school/studio/wizards/mfa_setup/. That path uses
        # `mfa_setup` (underscore), which the `/mfa/setup` (slash) check does NOT
        # match — so without exempting it, a no-device MFA-required user is bounced
        # off the very page where they enroll, producing an infinite
        # mfa/setup -> wizard -> mfa/setup loop (the new-owner onboarding loop).
        if (
            "/mfa/setup" in path
            or "/mfa/defer" in path
            or "/mfa/verify" in path
            or "/mfa/passkey/" in path
            or "wizards/mfa_setup" in path
            or "wizards/mfa_verify" in path
            # The MFA enforcement-policy page is where an admin switches this
            # tenant to grace/optional. In strict mode the wall would otherwise
            # gate that page too — a catch-22 where the toggle that disarms the
            # wall is itself behind the wall. Reachable here; writes stay gated
            # by settings.manage / control-plane inside the view.
            or "security/mfa-policy" in path
            # The service-worker reset escape hatch must always work — it only
            # clears the browser's stale SW/caches (no data exposure). Walling
            # it would trap a user with a stale worker AND no MFA device.
            or path == "/sw-reset"
        ):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice

            # config-resolver-allow: MFA enforcement tests patch this module symbol and drive this exact call path (Mock site namespace)
            site = get_effective_site_settings(request=request)
            require_all_staff = getattr(site, "require_mfa_all_staff", False)
            required_roles = getattr(site, "require_mfa_roles", None) or []

            # Augment tenant-configured roles with the platform baseline so
            # privileged roles (finance, super_admin, auditor, …) ALWAYS need
            # MFA even on tenants that forgot to configure it. See
            # apps/accounts/mfa_defaults.py.
            from apps.accounts.mfa_defaults import (
                effective_required_roles,
                principal_requires_strict_mfa,
                resolve_mfa_enforcement,
                resolve_operator_mfa,
            )

            # Operator + tenant, with floor: the operator's per-tenant policy is
            # OR-ed into "all staff" and unioned into the required roles above the
            # tenant's own settings; a tenant can only tighten, never weaken it,
            # and neither can drop below the baseline floor.
            operator_policy = resolve_operator_mfa(
                getattr(request, "school", None), request=request
            )
            role = get_user_role(user, getattr(request, "school", None))
            must_have_mfa = False
            if (require_all_staff or operator_policy.require_all_staff) and user.is_staff:
                must_have_mfa = True
            else:
                required_normalized = effective_required_roles(
                    required_roles, operator_required=operator_policy.required_roles
                )
                if role and str(role).strip().upper() in required_normalized:
                    must_have_mfa = True

            # Only a confirmed TOTP device or a passkey counts as configured MFA.
            # NOT django_otp's user_has_device(confirmed=True): that also counts a
            # StaticDevice (backup codes), and a backup-codes-only user can't
            # complete mfa_verify (it needs TOTP/passkey), so counting it would
            # wall them in a verify<->setup bounce.
            has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
            # WebAuthn/Passkey also counts as MFA (25.5, 29.1)
            if not has_device:
                from apps.accounts.models import UserPasskey

                has_device = UserPasskey.objects.filter(user=user).exists()

            # Enforcement posture is tenant-configurable (strict / grace /
            # optional) via the runtime-defaults cascade; the platform default
            # is strict (= the original hard wall). grace/optional let a
            # required user through with a persistent nudge instead of a
            # first-click wall — the Salesforce/Shopify rollout pattern.
            decision = resolve_mfa_enforcement(
                must_have_mfa=must_have_mfa,
                has_device=has_device,
                mode=(
                    "strict"
                    if principal_requires_strict_mfa(
                        user, getattr(request, "school", None)
                    )
                    else getattr(site, "mfa_enforcement_mode", None)
                ),
                grace_period_days=getattr(site, "mfa_grace_period_days", None),
                user=user,
            )
            if decision.action == "enforce":
                # A self-/admin-granted deferral ("skip MFA for N days") downgrades
                # the hard wall to a pass-through nudge — but ONLY for principals who
                # may be softened. A superuser / platform admin / active school owner
                # is already forced to strict above (principal_requires_strict_mfa
                # pins mode="strict"), so re-checking it here keeps the deferral from
                # ever letting an owner skip enrollment.
                from apps.accounts.mfa_deferral import mfa_setup_deferral_active

                if mfa_setup_deferral_active(user) and not principal_requires_strict_mfa(
                    user, getattr(request, "school", None)
                ):
                    request.rmc_mfa_nudge = {
                        "mode": "deferred",
                        "action": "nudge",
                        "grace_days_remaining": None,
                    }
                    return self.get_response(request)
                mfa_setup_url = reverse("accounts:mfa_setup")
                if path != mfa_setup_url.rstrip("/") and not path.endswith(
                    mfa_setup_url
                ):
                    # ``legacy=1`` routes to the polished, branded enrollment
                    # page (templates/accounts/partials/mfa_setup_page_body.html)
                    # via the sanctioned wizard-engine escape hatch, instead of
                    # the bare studio wizard.
                    return redirect(
                        mfa_setup_url
                        + "?legacy=1&next="
                        + (request.GET.get("next") or request.path)
                    )
                return self.get_response(request)
            if decision.action in ("grace", "nudge"):
                # Allowed through. Record the nudge for the banner context
                # processor and return immediately — never fall into the
                # re-verify gate below (there is no device to verify yet), or
                # the page would never render.
                request.rmc_mfa_nudge = {
                    "mode": decision.mode,
                    "action": decision.action,
                    "grace_days_remaining": decision.grace_days_remaining,
                }
                return self.get_response(request)

            # action == "none": device-holders (and non-required users) fall
            # through to the per-session re-verify gate.
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
        from apps.accounts.e2e_mfa_bypass import e2e_mfa_bypass_active

        if e2e_mfa_bypass_active(request):
            return True
        if request.session.get("mfa_verified"):
            return True
        # Durable device trust: a signed "remember this device" cookie survives a
        # session reset (pin flush, re-login, expiry) that would otherwise drop
        # session["mfa_verified"] and re-prompt the user. Re-establish the session
        # flag so the rest of this session skips the cookie check.
        try:
            from apps.accounts.mfa_device_trust import device_trust_valid

            if device_trust_valid(request, getattr(request, "user", None)):
                request.session["mfa_verified"] = True
                return True
        except Exception:  # noqa: BLE001 — trust check must never break the gate
            pass
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


class OnboardingEnforcementMiddleware:
    """Force admin-provisioned temp-password accounts through the set-password +
    profile-setup wizard before they can reach anything else.

    Airtight across sessions (not just at login): every authenticated page
    navigation is checked, so a flag flipped mid-session (or a user who bookmarked
    a deep link) is still routed to the wizard. Inert for every account whose
    ``needs_onboarding()`` is False — the overwhelming majority — so the hot path
    costs a single attribute read. Superusers/operators are left to their own
    Emergency-Lockdown flow and never trapped here. XHR/JSON requests pass through
    (the UI is gated anyway); only real HTML navigations are redirected.
    """

    _ALLOWED_VIEW_NAMES = frozenset(
        {
            "accounts:password_change",
            "accounts:password_change_done",
            "accounts:onboarding_profile",
            "accounts:logout",
            "logout",
            "set_language",
        }
    )
    _ALLOWED_PATH_PREFIXES = ("/static/", "/media/", "/health", "/i18n/", "/__debug__/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redirect_response = self._maybe_redirect(request)
        if redirect_response is not None:
            return redirect_response
        return self.get_response(request)

    def _maybe_redirect(self, request):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        # Operators/superusers use the Emergency-Lockdown login path — never trap them.
        if getattr(user, "is_superuser", False):
            return None
        try:
            if not user.needs_onboarding():
                return None
        except (AttributeError, DatabaseError):
            return None  # never break a request over this gate

        path = request.path_info or "/"
        if any(path.startswith(p) for p in self._ALLOWED_PATH_PREFIXES):
            return None
        # Gate real page navigations only; leave API/XHR alone.
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return None
        if request.method == "GET" and "text/html" not in request.headers.get(
            "accept", ""
        ):
            return None

        try:
            view_name = resolve(path).view_name
        except Resolver404:
            view_name = ""
        if view_name in self._ALLOWED_VIEW_NAMES:
            return None

        if getattr(user, "requires_password_change", False):
            target = reverse("accounts:password_change")
        elif not getattr(user, "profile_setup_completed", True):
            target = reverse("accounts:onboarding_profile")
        else:
            return None
        if request.path == target:
            return None
        return redirect(target)
