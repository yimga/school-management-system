"""
Multi-tenant middleware: resolve request host (subdomain or custom domain) to School,
set request.school and session school_id, and set PostgreSQL app.current_school_id for RLS.
"""

import logging
from django.conf import settings
from django.db import DatabaseError
from django.http import (
    HttpResponse,
    HttpResponseRedirect,
    HttpResponsePermanentRedirect,
)
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from apps.platform_runtime.helpers import get_effective_flags
from apps.platform_runtime.role_registry import (
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from apps.schools.host_routing import (
    get_canonical_base_domain,
    is_public_host,
    is_local_dev_host,
    map_legacy_host_to_canonical,
    public_host_kind,
)

logger = logging.getLogger(__name__)

# Paths that do not require a resolved school (Super Admin, static, health, etc.)
# /admin/ is NOT skipped: on base domain we resolve no tenant → Main (Public) Admin; on tenant subdomain we redirect to Backend
SUPER_PREFIXES = ("/super/",)
STATIC_PREFIXES = ("/static/", "/media/", "/favicon.ico", "/api/schema", "/offline/", "/sw.js", "/sw-asset-manifest.json")
HEALTH_PREFIXES = (
    "/health",
    "/ready",
    "/api/health",
    "/-/version",
    "/api/system/version",
    "/version.json",
)

# Legacy path-based tenancy marker kept for compatibility redirects only.
TENANT_PATH_PREFIX = "/t/"
MANAGER_ONLY_PREFIXES = (
    "/authentication/",
    "/super/",
    "/studio/",
    "/configuration/",
    "/ops/",
    "/internal-admin/",
    "/admin/",
    "/siteconfig/",
    "/backend/",
)
# Signup / first-run flows that must stay on the marketing apex (not manager host).
# Tenant sign-in is slug-host only — ``/authentication/login/`` on runmycampus.com
# redirects to ``/discover/`` (see ``APEX_TENANT_AUTH_DISCOVERY_PREFIXES``).
PUBLIC_TENANT_AUTH_PREFIXES = (
    "/authentication/onboarding/",
    "/authentication/mfa/",
    "/authentication/redirect/",
    "/authentication/school-picker/",
    "/verify-signup/",
)
# Apex marketing host must never render tenant login forms; hand off to discovery.
APEX_TENANT_AUTH_DISCOVERY_PREFIXES = (
    "/authentication/login",
    "/authentication/logout",
    "/authentication/password_reset",
    "/authentication/reset/",
    "/authentication/oidc",
    "/authentication/saml",
)
MANAGER_AUTH_ALLOWED_PREFIXES = (
    "/authentication/login/",
    "/authentication/logout/",
    "/authentication/redirect/",
    "/authentication/password_reset/",
    "/authentication/reset/",
    "/authentication/profile/",
    "/authentication/documentation/",
    "/authentication/notifications/",
    "/authentication/mfa/",
    "/authentication/impersonate/",
    "/authentication/end-impersonation/",
    "/authentication/oidc/",
    "/authentication/saml/",
)
MANAGER_HOST_ALLOWED_PREFIXES = (
    *MANAGER_AUTH_ALLOWED_PREFIXES,
    # First-run owner onboarding (token-authed) — parity with MANAGER_HOST_PUBLIC_ACCESS_PREFIXES.
    "/authentication/onboarding/",
    # Tenant-primary surface: must be allowlisted here so ReservedPublicHostAccessMiddleware
    # does not redirect to "/"; ManagerTenantPrimarySurfaceBlockMiddleware then redirects
    # authenticated users to the control-plane dashboard.
    "/authentication/backend/",
    "/verify-signup/",
    "/signup/",
    "/help/",
    "/help-center/",
    "/feature-center/",
    "/contact-us/",
    "/product-roadmap/",
    "/release-notes/",
    "/support/",
    "/feedback/",
    "/school/",
    "/teacher/",
    "/parent/",
    "/student/",
    "/super/voice-of-customer/",
    "/super/product-roadmap/",
    "/super/product-feedback/",
    "/status/",
    "/feedback-loop/",
    "/notifications/",
    "/kb/",
    "/super/",
    "/sales/",
    "/studio/",
    "/configuration/",
    "/api-center/",
    "/ops/",
    "/internal-admin/",
    "/admin/",
    "/siteconfig/",
    "/health",
    "/healthz/",
    "/ready/",
    "/status/",
    "/api/",
    "/-/version/",
    "/version.json",
    "/privacy/",
    "/terms/",
    "/cookie-policy/",
    "/demo/",
    "/resources/",
    "/static/",
    "/media/",
    "/favicon.ico",
    "/offline/",
    "/sw.js",
    "/sw-asset-manifest.json",
    "/platform-runtime/",
    # v4.02.34: assist-dock realtime/API (badges, SSE, presence) — manager shell loads
    # rmc-assist-dock.js; without this prefix ReservedPublicHostAccessMiddleware
    # 302s every /assist-dock/* call to "/" and breaks dock chrome on manager.
    "/assist-dock/",
)

MANAGER_HOST_PUBLIC_ACCESS_PREFIXES = (
    *MANAGER_AUTH_ALLOWED_PREFIXES,
    # First-run owner onboarding (token-authed; not an operator surface). Served
    # anonymously here too as defense-in-depth, so if the flow ever lands on the
    # manager host the control-plane gate doesn't force an operator login.
    "/authentication/onboarding/",
    "/verify-signup/",
    "/signup/",
    "/help/",
    "/help-center/",
    "/feature-center/",
    "/contact-us/",
    "/product-roadmap/",
    "/release-notes/",
    "/support/",
    "/feedback/",
    "/school/",
    "/teacher/",
    "/parent/",
    "/student/",
    "/super/voice-of-customer/",
    "/super/product-roadmap/",
    "/super/product-feedback/",
    "/status/",
    "/notifications/",
    "/offline/",
    "/sw.js",
    "/sw-asset-manifest.json",
    "/configuration/",
    "/internal-admin/",
    "/health",
    "/healthz/",
    "/ready/",
    "/status/",
    "/api/health/",
    # Machine cron trigger (Option 2) — authed by INTERNAL_CRON_TOKEN shared
    # secret in the view (constant-time), so an external scheduler can reach it
    # anonymously on the manager host just like /api/health/.
    "/api/internal/cron/",
    "/-/version/",
    "/api/system/version/",
    "/version.json",
    "/api/billing/processors/",
    "/api/observability/incidents/",
    "/static/",
    "/media/",
    "/favicon.ico",
    # Anonymous 24h share-link resolver (see assist_dock UnauthenticatedApiGuard exempt).
    "/assist-dock/s/",
    "/privacy/",
    "/terms/",
    "/cookie-policy/",
    "/demo/",
    "/resources/",
)

PUBLIC_ONLY_PREFIXES = (
    "/marketing/",
    "/product/",
    "/solutions/",
    "/pricing/",
    "/compare/",
    "/case-studies/",
    "/security-compliance/",
    "/integrations/",
    "/book-demo/",
    "/demo/",
    "/signup/",
    "/verify-signup/",
    "/api/trial/",
    "/onboard/",
    "/discover/",
    "/find/",
    "/verify/",
    "/support/",
    "/cm",
    "/ca",
)
VERIFY_HOST_ALLOWED_PREFIXES = (
    "/verify/",
    "/health",
    "/healthz/",
    "/ready/",
    "/status/",
    "/api/health/",
    "/static/",
    "/media/",
    "/favicon.ico",
    "/offline/",
    "/sw.js",
    "/sw-asset-manifest.json",
)


def _cache_get_optional(key, default=None):
    try:
        from django.core.cache import cache

        return cache.get(key, default)
    except (
        ImportError,
        AttributeError,
        TypeError,
        ConnectionError,
        ValueError,
        RuntimeError,
    ):
        return default


def _cache_delete_optional(key) -> bool:
    try:
        from django.core.cache import cache

        cache.delete(key)
        return True
    except (
        ImportError,
        AttributeError,
        TypeError,
        ConnectionError,
        ValueError,
        RuntimeError,
    ):
        return False


def _cache_set_optional(key, value, timeout=None) -> bool:
    try:
        from django.core.cache import cache

        cache.set(key, value, timeout)
        return True
    except (
        ImportError,
        AttributeError,
        TypeError,
        ConnectionError,
        ValueError,
        RuntimeError,
    ):
        return False


SUPPORT_HOST_ALLOWED_PREFIXES = (
    "/support/",
    "/discover/",
    "/find/",
    "/health",
    "/healthz/",
    "/ready/",
    "/status/",
    "/api/health/",
    "/static/",
    "/media/",
    "/favicon.ico",
    "/offline/",
    "/sw.js",
    "/sw-asset-manifest.json",
)


def _request_host_raw(request) -> str:
    """
    Return normalized host from request metadata without triggering Django's
    ALLOWED_HOSTS validation. This lets legacy-domain redirect logic run first.
    """
    forwarded = (request.META.get("HTTP_X_FORWARDED_HOST") or "").strip()
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
    else:
        candidate = (
            request.META.get("HTTP_HOST") or request.META.get("SERVER_NAME") or ""
        ).strip()
    if ":" in candidate:
        candidate = candidate.split(":", 1)[0].strip()
    return candidate.lower()


def _path_starts_with_tenant_prefix(path: str) -> bool:
    """True if path is under /t/<slug>/ (path-based tenant URL)."""
    path = (path or "").strip()
    if not path.startswith(TENANT_PATH_PREFIX):
        return False
    parts = [p for p in path.split("/") if p]
    return len(parts) >= 2 and parts[0] == "t"


def _extract_slug_from_tenant_path(path: str) -> str | None:
    """Extract school slug from /t/<slug>/... Return None if path is not /t/<slug>/..."""
    path = (path or "").strip()
    if not path.startswith(TENANT_PATH_PREFIX):
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2 or parts[0] != "t":
        return None
    return parts[1]


def _strip_tenant_path_prefix(path: str, slug: str) -> str:
    """Return path with /t/<slug> stripped. E.g. /t/default-school/authentication/login/ -> /authentication/login/."""
    prefix = f"/t/{slug}/"
    prefix_alt = f"/t/{slug}"
    if path.startswith(prefix):
        rest = path[len(prefix) :].strip("/")
        return f"/{rest}/" if rest else "/"
    if path == prefix_alt or path.startswith(prefix_alt + "/"):
        rest = path[len(prefix_alt) :].lstrip("/").strip("/")
        return f"/{rest}/" if rest else "/"
    return path


def _is_public_only_path(path: str) -> bool:
    path = (path or "").strip()
    if path in (
        "/cm",
        "/ca",
        "/onboard",
        "/discover",
        "/find",
        "/marketing",
        "/signup",
        "/support",
        "/verify",
    ):
        return True
    for prefix in PUBLIC_ONLY_PREFIXES:
        if (
            path == prefix
            or path.startswith(prefix.rstrip("/") + "/")
            or path.startswith(prefix)
        ):
            # Marketing demo pages use ``/demo/`` on the public host; tenant conversion uses
            # ``/demo/flow/`` on the school subdomain and must not bounce to the base domain.
            if path.startswith("/demo/flow"):
                continue
            return True
    return False


def _path_allowed_for_reserved_host(
    path: str, *, allowed_prefixes: tuple[str, ...]
) -> bool:
    path = (path or "").strip()
    if path in ("", "/"):
        return True
    for prefix in allowed_prefixes:
        if (
            path == prefix
            or path.startswith(prefix.rstrip("/") + "/")
            or path.startswith(prefix)
        ):
            return True
    return False


def _apex_auth_path_redirects_to_discovery(path: str) -> bool:
    normalized = (path or "").strip().lower()
    if not normalized:
        return False
    for prefix in APEX_TENANT_AUTH_DISCOVERY_PREFIXES:
        if (
            normalized == prefix.rstrip("/")
            or normalized.startswith(prefix if prefix.endswith("/") else f"{prefix}/")
        ):
            return True
    return False


def _is_manager_only_path(path: str) -> bool:
    path = (path or "").strip()
    for prefix in PUBLIC_TENANT_AUTH_PREFIXES:
        if (
            path == prefix
            or path.startswith(prefix.rstrip("/") + "/")
            or path.startswith(prefix)
        ):
            return False
    for prefix in MANAGER_ONLY_PREFIXES:
        if (
            path == prefix
            or path.startswith(prefix.rstrip("/") + "/")
            or path.startswith(prefix)
        ):
            return True
    return False


def _redirect_to_manager_host(request, path: str | None = None):
    base_domain = _get_base_domain()
    if not base_domain:
        return None
    scheme = "https" if request.is_secure() or not settings.DEBUG else "http"
    target_path = path if path is not None else request.get_full_path()
    if not str(target_path).startswith("/"):
        target_path = f"/{target_path}"
    return HttpResponseRedirect(f"{scheme}://manager.{base_domain}{target_path}")


PENDING_TENANT_AUTH_PREFIXES = (
    "/authentication/login",
    "/authentication/logout",
    "/authentication/password_reset",
    "/authentication/reset/",
    "/authentication/onboarding/",
    "/authentication/redirect/",
    "/authentication/mfa/",
    "/authentication/backend/",
    "/api/pending-provision/",
)


def _path_allows_pending_tenant_auth(path: str) -> bool:
    normalized = (path or "").strip().lower()
    if not normalized:
        return False
    return any(
        normalized == prefix.rstrip("/")
        or normalized.startswith(prefix if prefix.endswith("/") else f"{prefix}/")
        for prefix in PENDING_TENANT_AUTH_PREFIXES
    )


def _bind_pending_school_for_tenant_auth(request, subdomain: str | None):
    """
    Let owners sign in on ``{slug}.runmycampus.com`` while provisioning is pending.

    Returns True when ``request.school`` was bound and the request should continue.
    """
    token = (subdomain or "").strip()
    if not token or not _path_allows_pending_tenant_auth(request.path or ""):
        return False
    try:
        from apps.schools.pending_tenant_discovery import (
            lookup_school_by_slug_or_subdomain,
            pending_school_state,
        )
    except ImportError:
        return False
    school = lookup_school_by_slug_or_subdomain(token)
    if school is None or not pending_school_state(school):
        return False
    request.school = school
    request.tenant_provisioning_pending = True
    if getattr(request, "session", None) is not None:
        request.session["school_id"] = str(school.id)
    return True


def _redirect_unknown_school_slug(request, slug: str | None = None):
    base_domain = _get_base_domain()
    if not base_domain:
        from apps.schools.error_views import school_not_found

        return school_not_found(request)
    safe_slug = (slug or "").strip().lower()
    query = f"?slug={safe_slug}" if safe_slug else ""
    scheme = "https" if request.is_secure() or not settings.DEBUG else "http"
    return HttpResponseRedirect(f"{scheme}://{base_domain}/school-not-found/{query}")


def _response_for_unknown_tenant_host(request, slug: str | None = None):
    """Pending schools get an in-place setup page on their subdomain."""
    token = (slug or "").strip()
    if token:
        try:
            from apps.schools.pending_tenant_discovery import (
                lookup_school_by_slug_or_subdomain,
                pending_school_public_context,
                pending_school_state,
            )
        except ImportError:
            lookup_school_by_slug_or_subdomain = None  # type: ignore[assignment]
        if lookup_school_by_slug_or_subdomain is not None:
            school = lookup_school_by_slug_or_subdomain(token)
            if school is not None and pending_school_state(school):
                from django.shortcuts import render

                from apps.schools.pending_tenant_discovery import (
                    kick_pending_tenant_provisioning,
                )

                request.school = school
                request.tenant_provisioning_pending = True
                if getattr(request, "session", None) is not None:
                    request.session["school_id"] = str(school.id)
                if pending_school_state(school) == "provisioning":
                    kick_pending_tenant_provisioning(request, school)
                ctx = pending_school_public_context(school)
                ctx["school"] = school
                try:
                    from django.urls import reverse

                    ctx["provision_progress_api_url"] = request.build_absolute_uri(
                        reverse("api_public_pending_provision_progress")
                    )
                except Exception:
                    ctx["provision_progress_api_url"] = "/api/pending-provision/progress/"
                return render(
                    request,
                    "schools/tenant_setup_in_progress.html",
                    ctx,
                    status=202,
                )
    return _redirect_unknown_school_slug(request, slug)


class TenantHostMembershipMiddleware(MiddlewareMixin):
    """
    Enforce tenant-host membership after AuthenticationMiddleware.

    Must run AFTER ``AuthenticationMiddleware`` so ``request.user`` is populated.
    Works for both RLS (``TenantMiddleware``) and django-tenants stacks.
    """

    def process_request(self, request):
        school = getattr(request, "school", None)
        if not school:
            return None
        blocked = _enforce_tenant_host_membership(request, school)
        if blocked is not None:
            return blocked
        return None


def _extract_subdomain(host: str, base_domain: str | None) -> str | None:
    """
    Extract subdomain from host. E.g. ghs-limbe.yoursystem.com -> ghs-limbe.
    If base_domain is None, use the last two parts (e.g. yoursystem.com) and treat the rest as subdomain.
    """
    if not host:
        return None
    host = host.split(":")[0].lower()
    if base_domain and host.endswith("." + base_domain):
        sub = host[: -(len(base_domain) + 1)]
        return sub if sub else None
    parts = host.split(".")
    if len(parts) >= 3:
        return parts[0]
    return None


def _get_base_domain() -> str:
    """
    Canonical base domain for "no tenant" (main admin). Prefer MULTI_TENANT_BASE_DOMAIN;
    on Render when unset, use RENDER_EXTERNAL_HOSTNAME so the primary URL is always base domain.
    """
    return get_canonical_base_domain()


def _is_base_domain(host: str, base_domain: str) -> bool:
    """
    True if this host is the primary/base domain (no tenant subdomain).
    On base domain we never assign a tenant: Main (Public) Admin only; tenants use subdomain/custom domain.
    Also treat reserved public hosts as base/non-tenant hosts.
    """
    del base_domain  # compatibility with existing callers
    return is_public_host(host)


def _tenant_cache_key(host_or_sub: str, kind: str = "host") -> str:
    """Cache key for optional Redis tenant lookup (<10ms). Use kind='host' or 'subdomain'."""
    from apps.schools.tenant_resolution_cache import tenant_resolution_cache_key

    return tenant_resolution_cache_key(host_or_sub, kind)


class UrlConfSwitcherMiddleware(MiddlewareMixin):
    """
    Set request.urlconf to public_urls or tenant_urls so the root URL resolver
    serves the correct tree by host. Runs early (after Session).
    - base/verify/support -> config.public_urls
    - manager -> config.manager_urls
    - api -> config.api_urls
    - docs -> config.docs_urls
    - tenant subdomain/custom domain -> config.tenant_urls
    """

    def process_request(self, request):
        host = _request_host_raw(request)
        kind = public_host_kind(host)
        # Set early so templates (e.g. portal_base) can use it; manager urlconf has no 'kb' namespace.
        request.public_host_kind = kind
        # Local/test hosts keep full URL surface for developer workflows and legacy tests.
        if kind == "local":
            request.urlconf = "config.urls"
            return None
        if kind == "manager":
            request.urlconf = "config.manager_urls"
            return None
        if kind == "api":
            request.urlconf = "config.api_urls"
            return None
        if kind == "docs":
            request.urlconf = "config.docs_urls"
            return None
        base_domain = _get_base_domain()
        if _is_base_domain(host, base_domain):
            request.urlconf = "config.public_urls"
        else:
            request.urlconf = "config.tenant_urls"
        return None


class LegacyBaseDomainRedirectMiddleware(MiddlewareMixin):
    """
    Temporary backward-compat redirect: old base domains -> canonical base domain.
    Keeps deep links working during domain cutover.
    """

    def process_request(self, request):
        host = _request_host_raw(request)
        target_host = map_legacy_host_to_canonical(host)
        if not target_host:
            return None
        scheme = "https" if request.is_secure() or not settings.DEBUG else "http"
        return HttpResponsePermanentRedirect(
            f"{scheme}://{target_host}{request.get_full_path()}"
        )


class ReservedPublicHostAccessMiddleware(MiddlewareMixin):
    """
    Restrict verify/support reserved hosts to public-safe endpoints.
    """

    def process_request(self, request):
        host = _request_host_raw(request)
        path = (request.path or "").strip()
        kind = public_host_kind(host)
        request.public_host_kind = kind

        # Super-admin command center is canonical on manager.<base>.
        if kind is None and path.startswith("/super/"):
            forwarded = request.get_full_path()
            return _redirect_to_manager_host(request, path=forwarded)

        # /t/<slug>/ on base domain: always redirect to canonical subdomain (no path-based serving).
        if _path_starts_with_tenant_prefix(path):
            from apps.schools.models import School
            from apps.schools.tenant_url import build_tenant_backend_url

            slug = _extract_slug_from_tenant_path(path)
            school = None
            if slug:
                school = School.objects.filter(
                    slug__iexact=slug, is_active=True
                ).first()
                if not school:
                    school = School.objects.filter(
                        subdomain__iexact=slug, is_active=True
                    ).first()
            if not school:
                return _response_for_unknown_tenant_host(request, slug)
            inner = _strip_tenant_path_prefix(path, slug or "")
            return HttpResponsePermanentRedirect(
                build_tenant_backend_url(request, school, path=inner)
            )

        # Marketing apex is not a tenant sign-in surface — route to campus discovery.
        if kind == "base" and _apex_auth_path_redirects_to_discovery(path):
            return redirect("global_login_discovery")

        # Root/base domain is marketing-first: move operator/auth/admin paths to manager host.
        if kind == "base" and _is_manager_only_path(path):
            forwarded = request.get_full_path()
            return _redirect_to_manager_host(request, path=forwarded)

        if kind == "verify":
            if path in ("", "/"):
                return redirect("public_verify_hub")
            if not _path_allowed_for_reserved_host(
                path, allowed_prefixes=VERIFY_HOST_ALLOWED_PREFIXES
            ):
                return redirect("public_verify_hub")
            return None

        if kind == "support":
            if path in ("", "/"):
                return redirect("public_support_hub")
            if not _path_allowed_for_reserved_host(
                path, allowed_prefixes=SUPPORT_HOST_ALLOWED_PREFIXES
            ):
                return redirect("public_support_hub")
            return None

        if kind == "manager":
            if path in ("", "/"):
                return None
            if path.startswith("/verify-signup/") or path.startswith("/signup/"):
                from apps.schools.provision_email_urls import build_public_site_url

                return redirect(build_public_site_url(request.get_full_path()))
            if not _path_allowed_for_reserved_host(
                path, allowed_prefixes=MANAGER_HOST_ALLOWED_PREFIXES
            ):
                return HttpResponseRedirect("/")
            return None

        return None


class PublicPathRedirectMiddleware(MiddlewareMixin):
    """
    When a tenant host receives public-only paths, redirect to canonical public base host.
    """

    def process_request(self, request):
        host = _request_host_raw(request)
        if is_public_host(host):
            return None
        path = (request.path or "").strip()
        if not _is_public_only_path(path):
            return None
        base_domain = _get_base_domain()
        if not base_domain:
            return None
        scheme = "https" if request.is_secure() or not settings.DEBUG else "http"
        return HttpResponseRedirect(
            f"{scheme}://{base_domain}{request.get_full_path()}"
        )


def _resolve_school_from_request(request) -> "School | None":
    from apps.schools.models import School, SchoolDomain
    from django.conf import settings as django_settings

    cache_ttl = getattr(django_settings, "TENANT_CACHE_TTL", 300)

    host = _request_host_raw(request)
    base_domain = _get_base_domain()

    # Optional: Redis (or any cache backend) tenant lookup for <10ms resolution
    cached_id = _cache_get_optional(_tenant_cache_key(host, "host"))
    if cached_id:
        school = School.objects.filter(pk=cached_id, is_active=True).first()
        if school:
            return school

    # 1. Canonical verified domain registry (SchoolDomain)
    try:
        school_domain = (
            SchoolDomain.objects.select_related("school")
            .filter(domain__iexact=host, is_verified=True, school__is_active=True)
            .first()
        )
    except DatabaseError:
        school_domain = None
    if school_domain and school_domain.school_id:
        school = school_domain.school
        _cache_set_optional(_tenant_cache_key(host, "host"), str(school.id), cache_ttl)
        return school

    # 2. Legacy custom_domain fallback
    school = School.objects.filter(
        custom_domain__iexact=host,
        custom_domain_verified=True,
        is_active=True,
    ).first()
    if school:
        _cache_set_optional(_tenant_cache_key(host, "host"), str(school.id), cache_ttl)
        return school

    # 3. Subdomain
    subdomain = _extract_subdomain(host, base_domain or None)
    if subdomain:
        cached_id = _cache_get_optional(_tenant_cache_key(subdomain, "subdomain"))
        if cached_id:
            school = School.objects.filter(pk=cached_id, is_active=True).first()
            if school:
                return school
        school = School.objects.filter(
            subdomain__iexact=subdomain,
            is_active=True,
        ).first()
        if school:
            _cache_set_optional(
                _tenant_cache_key(subdomain, "subdomain"), str(school.id), cache_ttl
            )
            return school
        # Also match by slug
        school = School.objects.filter(
            slug__iexact=subdomain,
            is_active=True,
        ).first()
        if school:
            _cache_set_optional(
                _tenant_cache_key(subdomain, "subdomain"), str(school.id), cache_ttl
            )
            return school

    # Base/public hosts never resolve to tenant context.
    if _is_base_domain(host, base_domain):
        return None

    return None


def _get_single_tenant_school():
    """
    Backward-compatible helper used by older single-tenant tests.
    Returns the only active school when SINGLE_TENANT is enabled.
    """
    single_tenant_flag = (
        str(getattr(settings, "SINGLE_TENANT", "") or "").strip().lower()
    )
    if single_tenant_flag not in {"1", "true", "yes"}:
        return None

    from apps.schools.models import School

    schools = list(
        School.objects.filter(is_active=True).order_by("created_at", "id")[:2]
    )
    if len(schools) == 1:
        return schools[0]
    return None


def _resolve_bridge_school_fallback(request):
    """Resolve the tenant's School when the Client->School FK is unset.

    A freshly-provisioned schema tenant can have ``request.tenant.school`` None
    until the link is attached, which left ``request.school`` None for the WHOLE
    request — silently emptying every direct reader (setup-wizard tiles, copilot
    rail feeds, dashboard quick-actions seed, AI-chrome gate) and even risking a
    false "school not found". Resolve by the tenant's OWN identity (host
    subdomain), NEVER by user membership, so the bound school is always this
    tenant's own and a multi-membership user can never resolve the wrong one.
    Best-effort: returns None (preserving prior behavior) if anything fails.
    """
    try:
        from apps.schools.pending_tenant_discovery import (
            lookup_school_by_slug_or_subdomain,
        )
    except ImportError:
        return None
    subdomain = _extract_subdomain(
        _request_host_raw(request), _get_base_domain() or None
    )
    if not subdomain:
        return None
    try:
        school = lookup_school_by_slug_or_subdomain(subdomain)
    except Exception:  # noqa: BLE001 — bridge fallback must never break request setup
        return None
    if school is not None and getattr(school, "id", None) is not None:
        return school
    return None


class TenantSchemaSchoolBridgeMiddleware(MiddlewareMixin):
    """
    When using django-tenants (schema-per-tenant), TenantMainMiddleware sets request.tenant (Client).
    This bridge sets request.school = request.tenant.school so all code that expects request.school works.
    Must run immediately after TenantMainMiddleware.
    """

    def process_request(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None and hasattr(tenant, "school"):
            school = tenant.school
            if school is None:
                # Client->School FK not attached yet (freshly provisioned tenant):
                # resolve by tenant identity (subdomain) so every downstream
                # request.school reader works instead of degrading to an empty
                # surface. Common case (FK present) skips this entirely.
                school = _resolve_bridge_school_fallback(request)
            request.school = school
            if request.school and getattr(request, "session", None) is not None:
                request.session["school_id"] = str(request.school.id)
        else:
            request.school = None


class TenantSchoolNotFoundMiddleware(MiddlewareMixin):
    """
    When using django-tenants: if the host looks like a tenant host (not base domain)
    but no tenant was resolved (request.school is None), return branded "School Not Found" 404.
    Must run after TenantSchemaSchoolBridgeMiddleware. Skip public paths (static, health, discover, marketing, etc.).
    """

    def process_request(self, request):
        path = (request.path or "").strip()
        for prefix in (
            SUPER_PREFIXES
            + STATIC_PREFIXES
            + HEALTH_PREFIXES
            + (
                "/discover/",
                "/marketing/",
                "/signup/",
                "/verify-signup/",
                "/api/caddy-check/",
                "/api/v1/auth/check-domain/",
                "/api/trial/",
            )
        ):
            if path.startswith(prefix) or path == prefix.rstrip("/"):
                return None
        if getattr(request, "school", None) is not None:
            return None
        host = _request_host_raw(request)
        base_domain = _get_base_domain()
        if _is_base_domain(host, base_domain):
            return None
        subdomain = _extract_subdomain(host, base_domain or None)
        if _bind_pending_school_for_tenant_auth(request, subdomain):
            return None
        return _response_for_unknown_tenant_host(request, subdomain)


def _resolve_login_discovery_path() -> str:
    """Named URL for cross-tenant redirect; safe when ROOT_URLCONF lacks marketing routes."""
    from django.urls import NoReverseMatch, reverse

    for name in ("global_login_discovery", "accounts:login"):
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return "/authentication/login/"


def _enforce_tenant_host_membership(request, school):
    """
    On a tenant subdomain, authenticated users must belong to that school.

    Platform operators (control-plane access) may cross for support; everyone
    else is redirected to the public login host.
    """
    user = getattr(request, "user", None)
    if not school or not user or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return None
    try:
        from apps.schools.control_plane import user_has_control_plane_access

        if user_has_control_plane_access(user):
            return None
    except ImportError:
        pass
    path = (getattr(request, "path", "") or "").strip()
    allowed_prefixes = (
        "/authentication/login/",
        "/authentication/logout/",
        "/authentication/password_reset/",
        "/authentication/reset/",
        "/authentication/onboarding/",
        "/verify-signup/",
        "/static/",
        "/media/",
        "/health",
        "/healthz/",
        "/favicon.ico",
    )
    for prefix in allowed_prefixes:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return None
    try:
        from apps.schools.models import SchoolMembership

        if SchoolMembership.objects.filter(user=user, school=school).exists():
            return None
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        return None
    from django.contrib import messages
    from django.shortcuts import redirect

    from apps.schools.provision_email_urls import build_public_site_url

    messages.warning(
        request,
        "You do not have access to this school's portal. Sign in with your school account.",
        fail_silently=True,
    )
    request.session.pop("school_id", None)
    return redirect(build_public_site_url(_resolve_login_discovery_path()))


class TenantMiddleware(MiddlewareMixin):
    """
    Resolve the current school from the request host (subdomain or custom domain).
    Sets request.school, request.session['school_id'], and PostgreSQL app.current_school_id.
    (Not used when USE_DJANGO_TENANTS=1; TenantMainMiddleware + TenantSchemaSchoolBridgeMiddleware are used instead.)
    """

    def process_request(self, request):
        path = request.path or ""

        # Skip paths that don't need a school (except /admin/: we resolve tenant so we can redirect tenant /admin/ to Backend)
        for prefix in SUPER_PREFIXES + STATIC_PREFIXES + HEALTH_PREFIXES:
            if path.startswith(prefix):
                request.school = None
                return None

        host = _request_host_raw(request)
        base_domain = _get_base_domain()
        from apps.schools.models import School

        # Compatibility window: old /t/<slug>/ links permanently redirect to canonical tenant subdomain URLs.
        if _path_starts_with_tenant_prefix(path):
            slug = _extract_slug_from_tenant_path(path)
            school = None
            if slug:
                school = School.objects.filter(
                    slug__iexact=slug, is_active=True
                ).first()
                if not school:
                    school = School.objects.filter(
                        subdomain__iexact=slug, is_active=True
                    ).first()
            if not school:
                return _response_for_unknown_tenant_host(request, slug)
            from apps.schools.tenant_url import build_tenant_backend_url

            inner_path = _strip_tenant_path_prefix(path, slug or "")
            return HttpResponsePermanentRedirect(
                build_tenant_backend_url(request, school, path=inner_path)
            )

        # Resolve school from host (subdomain/custom domain) or from session when not on base domain
        try:
            school = _resolve_school_from_request(request)
            if school is None and request.session.get("school_id"):
                host_kind = getattr(request, "public_host_kind", None) or public_host_kind(
                    host
                )
                normalized_host = (host or "").strip().lower()
                allow_session_school = (
                    not _is_base_domain(host, base_domain)
                    or is_local_dev_host(host)
                    or host_kind == "manager"
                    or normalized_host.startswith("manager.")
                )
                if allow_session_school:
                    school = School.objects.filter(
                        id=request.session["school_id"],
                        is_active=True,
                    ).first()
        except (AttributeError, DatabaseError, KeyError, TypeError, ValueError) as e:
            logger.warning("Tenant resolution failed: %s", e, exc_info=True)
            school = None

        # Unknown tenant host (subdomain/custom host not in DB): setup page or auth bypass.
        if school is None and not _is_base_domain(host, base_domain):
            subdomain = _extract_subdomain(host, base_domain or None)
            if _bind_pending_school_for_tenant_auth(request, subdomain):
                school = getattr(request, "school", None)
            else:
                return _response_for_unknown_tenant_host(request, subdomain)

        request.school = school
        # Tenant backend admin dashboard: on tenant subdomain /admin/ -> redirect to tenant Backend URL
        if school and path.startswith("/admin/"):
            try:
                from apps.schools.tenant_url import build_tenant_backend_url

                return HttpResponseRedirect(
                    build_tenant_backend_url(
                        request, school, path="/authentication/backend/"
                    )
                )
            except (AttributeError, ImportError, TypeError, ValueError):
                pass
        if school:
            request.session["school_id"] = str(school.id)
            try:
                from django.utils import timezone as tz
                from apps.siteconfig.tenant_config import get_tenant_locale

                locale = get_tenant_locale(school=school)
                tz.activate(
                    locale.get("timezone") or locale.get("default_timezone") or "UTC"
                )
            except (AttributeError, ImportError, TypeError, ValueError) as e:
                logger.debug("Could not activate school timezone: %s", e)
            try:
                if not getattr(settings, "USE_DJANGO_TENANTS", False):
                    from apps.schools.rls_context import set_rls_school_id

                    set_rls_school_id(school.id)
                    request._rls_school_id_set = True
            except DatabaseError as e:
                logger.debug("Could not set app.current_school_id: %s", e)
        else:
            normalized_host = (host or "").strip().lower()
            host_kind = getattr(request, "public_host_kind", None) or public_host_kind(
                host
            )
            on_manager_host = (
                host_kind == "manager" or normalized_host.startswith("manager.")
            )
            if not on_manager_host:
                request.session.pop("school_id", None)

        return None

    def process_response(self, request, response):
        """Reset RLS GUC so the session does not leak to other requests (e.g. connection pool)."""
        if getattr(request, "_rls_school_id_set", False):
            try:
                from apps.schools.rls_context import (
                    quarantine_rls_connection,
                    reset_rls_school_id,
                )

                reset_rls_school_id()
            except DatabaseError as e:
                logger.debug("Could not reset app.current_school_id: %s", e)
                quarantine_rls_connection(str(e))
            request._rls_school_id_set = False
        return response


def _reset_rls_school_id_if_set(request):
    """Reset app.current_school_id when this request had set it. Used on exception path."""
    if not getattr(request, "_rls_school_id_set", False):
        return
    try:
        from apps.schools.rls_context import (
            quarantine_rls_connection,
            reset_rls_school_id,
        )

        reset_rls_school_id()
    except DatabaseError as e:
        logger.debug("Could not reset app.current_school_id (finally): %s", e)
        quarantine_rls_connection(str(e))
    request._rls_school_id_set = False


class RlsResetOnExceptionMiddleware(MiddlewareMixin):
    """
    Ensures app.current_school_id is RESET even when a view or inner middleware raises.
    Must be placed immediately after TenantMiddleware. No-op when USE_DJANGO_TENANTS=1.
    """

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            _reset_rls_school_id_if_set(request)


# Section 8.6: Paths that are always allowed when school is frozen (Caddy, discovery, LTI, health, logout, frozen page)
FROZEN_EXEMPT_PREFIXES = (
    "/api/caddy-check/",
    "/discover/",
    "/lti/",
    "/super/",
    "/static/",
    "/media/",
    "/health",
    "/healthz/",
    "/ready/",
    "/status/",
    "/account-frozen/",
    "/authentication/logout/",
)

# Section 8.6 — "do no harm" carve-out (billing/subscription program).
# HTTP methods that cannot mutate state. During a commercial freeze ONLY these
# are permitted for learner roles — the load-bearing write-protection invariant.
# POST/PUT/PATCH/DELETE always fall through to the freeze block, so no write path
# is ever opened while a school is frozen.
FROZEN_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Learner roles that keep READ-ONLY access during a commercial freeze, so a
# school's billing/storage lapse never locks students, parents, and teachers out
# of learning, grades, attendance, and messages. Sourced from the role registry
# (no hardcoded role strings). Admin / owner / finance roles are deliberately
# ABSENT — they must hit the freeze block and act on the overdue account.
FROZEN_READONLY_ROLES = frozenset(
    {ROLE_STUDENT, ROLE_PARENT, ROLE_TEACHER}
)

# Commercial freeze reasons eligible for the do-no-harm carve-out. Both current
# reasons (BILLING / STORAGE) and the unspecified default are non-punitive; a
# future legal/abuse freeze reason would NOT inherit read-only access.
FROZEN_DO_NO_HARM_REASONS = frozenset({"BILLING", "STORAGE", ""})


def frozen_readonly_access_allowed(request, school):
    """True when a frozen-school request qualifies for the do-no-harm read-only
    carve-out: the operator has it enabled, the freeze reason is a commercial one
    (billing/storage), the request is a safe (non-mutating) method, AND the
    authenticated user holds a learner role. Never opens a write path — writes are
    rejected by the safe-method gate before any other check matters.

    Config/billing/admin surfaces need no path denylist here: they already require
    ``settings.manage`` (or staff), which learner roles lack, so RBAC returns 403
    independently. The shared role-aware backend dashboard is intentionally
    reachable so teachers keep read access during a lapse.
    """
    if not getattr(settings, "BILLING_FREEZE_DO_NO_HARM", True):
        return False
    reason = (getattr(school, "frozen_reason", "") or "").strip().upper()
    configured = getattr(settings, "BILLING_FREEZE_DO_NO_HARM_REASONS", None)
    eligible = (
        frozenset(str(r).strip().upper() for r in configured)
        if configured is not None
        else FROZEN_DO_NO_HARM_REASONS
    )
    if reason not in eligible:
        return False
    method = (getattr(request, "method", "") or "").upper()
    if method not in FROZEN_SAFE_METHODS:
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    role = (getattr(user, "role", "") or "").strip().upper()
    return role in FROZEN_READONLY_ROLES


class TenantFreezeMiddleware(MiddlewareMixin):
    """
    Section 8.6: When request.school is set and school.is_frozen is True, redirect to
    /account-frozen/ except for exempt paths. Staff/superuser can bypass to access billing/super.

    Do-no-harm carve-out: during a commercial freeze (billing/storage), learner
    roles (student/parent/teacher) keep READ-ONLY access — safe-method requests
    pass through so a school's lapse never locks students, parents, and teachers
    out of learning, grades, attendance, and messages. Any write, and any
    admin/owner/finance role, still hits the freeze block and is redirected to the
    account-frozen page (which explains how to restore the account). The carve-out
    is operator-configurable via ``BILLING_FREEZE_DO_NO_HARM`` (default on).

    Must run after TenantMiddleware and AuthenticationMiddleware.
    """

    def process_request(self, request):
        path = (request.path or "").strip()
        for prefix in FROZEN_EXEMPT_PREFIXES:
            if path.startswith(prefix) or path == prefix.rstrip("/"):
                return None
        # Allow staff/superuser to bypass freeze (e.g. to access billing or super admin)
        if getattr(request, "user", None) and request.user.is_authenticated:
            if getattr(request.user, "is_staff", False) or getattr(
                request.user, "is_superuser", False
            ):
                return None
        school = getattr(request, "school", None)
        if not school or not getattr(school, "is_frozen", False):
            return None
        # Do-no-harm: learner roles keep read-only access during a commercial
        # freeze; writes and admin roles fall through to the block below.
        if frozen_readonly_access_allowed(request, school):
            return None
        from django.shortcuts import redirect

        return redirect("account_frozen")


class ModuleActivationMiddleware(MiddlewareMixin):
    """
    World Engine E.2: Set request.active_modules from get_tenant_modules(school).
    Single source for active modules; sidebar and feature gates use this or is_feature_enabled.
    """

    def process_request(self, request):
        school = getattr(request, "school", None)
        if school is None:
            request.active_modules = []
            return None
        try:
            from apps.siteconfig.tenant_config import get_tenant_modules

            request.active_modules = get_tenant_modules(school)
        except (AttributeError, ImportError, TypeError, ValueError):
            request.active_modules = []
        return None


class TenantApiQuotaMiddleware(MiddlewareMixin):
    """
    Plan I: Per-tenant API rate limit. Runs after TenantMiddleware.
    When request.school is set and path is under /api/, enforces throttle_tenant_request.
    Set API_TENANT_MAX_REQUESTS_PER_MINUTE in settings (default 600). Disable with DISABLE_TENANT_API_QUOTA=1.
    """

    def process_request(self, request):
        if getattr(settings, "DISABLE_TENANT_API_QUOTA", False):
            return None
        path = (request.path or "").strip()
        if not path.startswith("/api/"):
            return None
        school = getattr(request, "school", None)
        if not school:
            return None
        try:
            from apps.api.rate_limit import throttle_tenant_request

            allowed, retry_after = throttle_tenant_request(request)
            if not allowed:
                from django.http import JsonResponse

                return JsonResponse(
                    {
                        "detail": "Request limit exceeded for this school. Retry later.",
                        "retry_after": retry_after,
                    },
                    status=429,
                    headers={"Retry-After": str(retry_after)} if retry_after else None,
                )
        except (AttributeError, ImportError, TypeError, ValueError) as e:
            logger.debug("Tenant API quota check failed: %s", e)
        return None


class SentryTenantTagMiddleware(MiddlewareMixin):
    """Phase H optional: tag Sentry events with school_id when request.school is set."""

    def process_request(self, request):
        school = getattr(request, "school", None)
        if school:
            from apps.observability.tracing import set_tags

            set_tags(
                school_id=getattr(school, "id", ""),
                school_slug=getattr(school, "slug", "") or "",
            )
        return None


class TenantLastActivityMiddleware(MiddlewareMixin):
    """Phase H optional: update School.last_activity when request.school is set (throttled ~1/hour per school)."""

    def process_response(self, request, response):
        school = getattr(request, "school", None)
        if not school or not getattr(school, "id", None):
            return response
        try:
            from django.core.cache import cache
            from django.utils import timezone

            cache_key = f"school_last_activity:{school.id}"
            if cache.get(cache_key):
                return response
            cache.set(cache_key, True, timeout=3600)  # magic-number-allow: cache-ttl-seconds
            from apps.schools.models import School

            School.objects.filter(pk=school.id).update(last_activity=timezone.now())
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
            pass
        return response


class TenantSuperAdminRequiredMiddleware(MiddlewareMixin):
    """
    Restrict /super/ to users with SUPERADMIN role or is_superuser.
    Must run after AuthenticationMiddleware. Add after TenantMiddleware.
    """

    def process_request(self, request):
        if not request.path.startswith("/super/"):
            return None
        # Global toggle: when Super Admin UI is disabled, block /super/.
        try:
            flags = get_effective_flags(request)
            if not flags.get("enable_super_admin_ui", True):
                from django.http import HttpResponseForbidden

                return HttpResponseForbidden("Super Admin is disabled.")
        except (AttributeError, TypeError, ValueError):
            pass
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        try:
            from apps.schools.control_plane import user_has_control_plane_access
        except ImportError:
            user_has_control_plane_access = None
        if callable(user_has_control_plane_access) and user_has_control_plane_access(
            request.user
        ):
            return None
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("Super Admin access required.")


class ManagerHostControlPlaneRequiredMiddleware(MiddlewareMixin):
    """
    Require a platform operator for manager-host surfaces outside the public/auth bootstrap paths.

    This prevents tenant staff users from treating manager.runmycampus.com as a
    generic staff host and closes the gap where a missed decorator could expose
    global tenant data.
    """

    def process_request(self, request):
        if getattr(request, "public_host_kind", None) != "manager":
            return None

        path = (request.path or "").strip()
        if path in ("", "/"):
            if not getattr(request.user, "is_authenticated", False):
                return None
        elif _path_allowed_for_reserved_host(
            path, allowed_prefixes=MANAGER_HOST_PUBLIC_ACCESS_PREFIXES
        ):
            return None

        if not getattr(request.user, "is_authenticated", False):
            # Single entry (Salesforce/Shopify model): unauthenticated /admin/ → /super/ so one sign-in URL.
            if path.startswith("/admin"):
                from django.urls import reverse

                return redirect(reverse("super:dashboard"))
            from apps.platform_runtime.middleware_unauthenticated_api_guard import (
                path_requires_unauthenticated_api_auth,
            )

            if path_requires_unauthenticated_api_auth(path, request.method):
                return HttpResponse(status=401)
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())

        try:
            from apps.schools.control_plane import user_has_control_plane_access
        except ImportError:
            user_has_control_plane_access = None

        if callable(user_has_control_plane_access) and user_has_control_plane_access(
            request.user
        ):
            return None

        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("Control-plane access required.")


class SuperAdminRateLimitMiddleware(MiddlewareMixin):
    """
    Control plane hardening (12.7): rate limit /super/ to 120 requests per user per minute.
    Stricter cap for POST /super/native-roster-connectors/ (credential probes).
    Returns 429 Too Many Requests with Retry-After: 60 when exceeded.
    """

    MINUTE_LIMIT = 120
    NATIVE_ROSTER_POST_PER_MINUTE = 25

    def process_request(self, request):
        if not request.path.startswith("/super/"):
            return None
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        from django.core.cache import cache
        from django.utils import timezone
        from django.http import HttpResponse

        if (
            request.method == "POST"
            and "native-roster-connectors" in request.path
        ):
            nk = "super_native_rl:{}:{}".format(
                request.user.pk,
                timezone.now().strftime("%Y%m%d%H%M"),
            )
            try:
                nc = cache.get(nk, 0)
                if nc >= self.NATIVE_ROSTER_POST_PER_MINUTE:
                    r = HttpResponse("Too Many Requests (native roster console)", status=429)
                    r["Retry-After"] = "60"
                    return r
                cache.set(nk, nc + 1, timeout=120)
            except (AttributeError, TypeError, ValueError):
                pass

        key = "super_rl:{}:{}".format(
            request.user.pk,
            timezone.now().strftime("%Y%m%d%H%M"),
        )
        try:
            count = cache.get(key, 0)
            if count >= self.MINUTE_LIMIT:
                r = HttpResponse("Too Many Requests", status=429)
                r["Retry-After"] = "60"
                return r
            cache.set(key, count + 1, timeout=120)
        except (AttributeError, TypeError, ValueError):
            pass
        return None


# -----------------------------------------------------------------------------
# Phase D: Feature gate and plan enforcement
# -----------------------------------------------------------------------------

# Path prefix (or exact path) -> feature code required. Empty = no gate for that path.
# Phase D polish: gate design_studio, inventory, library, transport when those routes exist.
FEATURE_GATE_PATH_MAP = {
    "/portal/design-studio/": "design_studio",
    "/portal/design-studio": "design_studio",
    "/portal/features/inventory/": "inventory",
    "/portal/features/inventory": "inventory",
    "/portal/features/library/": "library",
    "/portal/features/library": "library",
    "/portal/features/transport/": "transport",
    "/portal/features/transport": "transport",
}

# Path prefix -> capability codes; request is allowed if **any** code is enabled.
# Batch 14+ report SKUs: ministry paths accept ``reports_ministry_exports`` or coarse ``reports``;
# parent report downloads accept ``reports_pdf_exports`` or coarse ``reports``;
# custom builder surfaces accept ``reports_custom_builder`` or coarse ``reports``;
# scheduled delivery hub/API accept ``reports_scheduled_delivery`` or coarse ``reports``
# (see billing_sku_registry / BILLING_SKUS_ENTITLEMENTS.md).
# Uses ``is_plan_entitlement_feature_enabled`` (plan/addons/School.features only) so BASE_SCHOOL
# manifest ``reports`` does not bypass SKU gating. ``/analytics/`` uses code ``analytics`` only
# (BR-10 Intelligence tier — not granted by core module manifest).
FEATURE_GATE_PATH_ANY_OF: dict[str, tuple[str, ...]] = {
    "/reports/regulatory-export/": ("reports_ministry_exports", "reports"),
    "/reports/regulatory-export": ("reports_ministry_exports", "reports"),
    "/reports/statistical-return/": ("reports_ministry_exports", "reports"),
    "/reports/statistical-return": ("reports_ministry_exports", "reports"),
    # Staff publish / promotion flows (still @staff_member_required; plan must include coarse reports).
    "/reports/publish/": ("reports",),
    "/reports/publish": ("reports",),
    "/reports/promotion-preview/": ("reports",),
    "/reports/promotion-preview": ("reports",),
    # Parent term/annual report downloads (PDF/CSV under this prefix; see reports.urls).
    "/reports/parent/report/": ("reports_pdf_exports", "reports"),
    "/reports/parent/report": ("reports_pdf_exports", "reports"),
    # Report card builder + style previews (siteconfig.urls); API ad-hoc report definitions (urls_v1).
    "/siteconfig/reports/builder/": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/builder": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/preview/": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/preview": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/embed-preview/": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/embed-preview": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/live-preview/": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/live-preview": ("reports_custom_builder", "reports"),
    # Template download + bulk letter merge (siteconfig.urls); same SKU family as builder.
    "/siteconfig/reports/download/": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/download": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/bulk-letters/": ("reports_custom_builder", "reports"),
    "/siteconfig/reports/bulk-letters": ("reports_custom_builder", "reports"),
    "/api/v1/reports/adhoc": ("reports_custom_builder", "reports"),
    "/api/v1/reports/adhoc/": ("reports_custom_builder", "reports"),
    # Scheduled delivery hub (siteconfig) + API discovery list (see views_v1.ScheduledReportsListView).
    "/siteconfig/reports/scheduled/": ("reports_scheduled_delivery", "reports"),
    "/siteconfig/reports/scheduled": ("reports_scheduled_delivery", "reports"),
    "/api/v1/reports/scheduled": ("reports_scheduled_delivery", "reports"),
    "/api/v1/reports/scheduled/": ("reports_scheduled_delivery", "reports"),
    # Ministry / EMIS API (same SKU family as HTML regulatory/statistical paths).
    "/api/v1/reports/regulatory-presets": ("reports_ministry_exports", "reports"),
    "/api/v1/reports/regulatory-presets/": ("reports_ministry_exports", "reports"),
    "/api/v1/reports/regulatory-export": ("reports_ministry_exports", "reports"),
    "/api/v1/reports/regulatory-export/": ("reports_ministry_exports", "reports"),
    "/api/v1/reports/emis": ("reports_ministry_exports", "reports"),
    "/api/v1/reports/emis/": ("reports_ministry_exports", "reports"),
    # Intelligence tier (BR-10): tenant analytics app — not implied by core module manifest.
    "/analytics/": ("analytics",),
    "/analytics": ("analytics",),
}


def _feature_gate_path_matches(path: str, prefix: str) -> bool:
    p = (prefix or "").strip()
    if not p:
        return False
    base = p.rstrip("/")
    return path == p or path == base or path.startswith(base + "/")


def _school_has_capability(request, school, code: str) -> bool:
    try:
        from apps.policies.policy_registry import get_effective_policy

        policy_result = get_effective_policy(
            school,
            user=getattr(request, "user", None),
            capability=code,
        )
        if isinstance(policy_result, dict):
            return bool(policy_result.get("enabled", False))
    except (AttributeError, ImportError, TypeError, ValueError):
        pass
    from apps.schools.models import is_feature_enabled

    return is_feature_enabled(school, code)


def _feature_gate_403(request, feature_code: str):
    """Return 403 response (JSON for API, HTML for browser)."""
    from django.http import HttpResponseForbidden, JsonResponse

    if (
        request.path.startswith("/api/")
        or (request.headers.get("Accept") or "").find("application/json") >= 0
    ):
        return JsonResponse(
            {
                "error": "feature_not_available",
                "feature": feature_code,
                "detail": "This feature is not enabled for your plan.",
            },
            status=403,
        )
    return HttpResponseForbidden(
        f"<h1>403 Forbidden</h1><p>This feature ({feature_code}) is not enabled for your plan. Contact your administrator or upgrade.</p>"
    )


class FeatureGatekeeperMiddleware(MiddlewareMixin):
    """
    Phase D / Batch 14+: Enforce feature access by path when ``request.school`` is set.
    ``FEATURE_GATE_PATH_MAP`` — single capability per prefix.
    ``FEATURE_GATE_PATH_ANY_OF`` — prefix allowed if **any** listed capability is enabled.
    Uses ``get_effective_policy`` when available, else ``is_feature_enabled``.
    Must run after TenantMiddleware.
    """

    def process_request(self, request):
        path = (request.path or "").strip()
        school = getattr(request, "school", None)
        if not school:
            return None
        for prefix, code in FEATURE_GATE_PATH_MAP.items():
            if not code:
                continue
            if _feature_gate_path_matches(path, prefix):
                if not _school_has_capability(request, school, code):
                    return _feature_gate_403(request, code)
                return None
        for prefix, codes in FEATURE_GATE_PATH_ANY_OF.items():
            if not codes:
                continue
            if _feature_gate_path_matches(path, prefix):
                from apps.schools.models import is_plan_entitlement_feature_enabled

                if not any(is_plan_entitlement_feature_enabled(school, c) for c in codes):
                    return _feature_gate_403(request, codes[0])
                return None
        return None


class DynamicThemeMiddleware(MiddlewareMixin):
    """
    Phase B: Set request.admin_theme_choice from school.theme_choice so admin/base
    can serve Unfold/Jazzmin/Sneat per tenant. Run after TenantMiddleware.
    """

    def process_request(self, request):
        school = getattr(request, "school", None)
        if school and getattr(school, "theme_choice", None):
            request.admin_theme_choice = school.theme_choice.strip().upper()
            if request.admin_theme_choice not in ("UNFOLD", "JAZZMIN", "SNEAT"):
                request.admin_theme_choice = "UNFOLD"
        else:
            request.admin_theme_choice = getattr(
                request, "admin_theme_choice", "UNFOLD"
            )
        return None


class UsageLimitMiddleware(MiddlewareMixin):
    """
    Phase D (optional): Enforce Plan max_students / max_staff. Enable with
    ENABLE_USAGE_LIMIT_MIDDLEWARE=True. When over limit, returns 403 with message.
    """

    def process_request(self, request):
        import os

        if os.getenv("DISABLE_USAGE_LIMIT_MIDDLEWARE", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            return None
        school = getattr(request, "school", None)
        if not school:
            return None
        # Phase E: Skip usage limits for waived schools (full access)
        if getattr(school, "billing_type", None) in (
            "COMPLIMENTARY",
            "MANUAL_OVERRIDE",
        ):
            return None
        plan = getattr(school, "plan", None)
        if not plan:
            return None
        from django.http import JsonResponse, HttpResponseForbidden

        if getattr(plan, "max_students", None) is not None:
            from apps.people.models import StudentProfile

            count = StudentProfile.objects.filter(school=school).count()
            if count >= plan.max_students:
                if (
                    request.path.startswith("/api/")
                    or (request.headers.get("Accept") or "").find("application/json")
                    >= 0
                ):
                    return JsonResponse(
                        {
                            "error": "usage_limit",
                            "limit": "max_students",
                            "detail": "Student limit reached for your plan.",
                        },
                        status=403,
                    )
                return HttpResponseForbidden(
                    "<h1>403</h1><p>Student limit reached for your plan. Please upgrade.</p>"
                )
        if getattr(plan, "max_staff", None) is not None:
            from apps.people.models import TeacherProfile

            count = TeacherProfile.objects.filter(school=school).count()
            if count >= plan.max_staff:
                if (
                    request.path.startswith("/api/")
                    or (request.headers.get("Accept") or "").find("application/json")
                    >= 0
                ):
                    return JsonResponse(
                        {
                            "error": "usage_limit",
                            "limit": "max_staff",
                            "detail": "Staff limit reached for your plan.",
                        },
                        status=403,
                    )
                return HttpResponseForbidden(
                    "<h1>403</h1><p>Staff limit reached for your plan. Please upgrade.</p>"
                )
        return None


class TenantLocaleMiddleware(MiddlewareMixin):
    """Local-first: activate the resolved tenant's timezone (and its default language for
    visitors with no explicit preference) so dates/times and anonymous copy render in the
    SCHOOL's locale instead of the global platform default.

    Before this, ``School.timezone`` / ``School.default_language`` were stored but never
    applied — every page rendered in the platform ``TIME_ZONE`` / ``LANGUAGE_CODE``.

    Stronger language signals always win: a language cookie, a matched ``Accept-Language``,
    or an authenticated user's saved preference (``AssistDockLocaleMiddleware`` runs
    earlier in the chain). This only fills the gap where the resolved language is still the
    bare platform default. Timezone is reset on response/exception so a pooled worker
    thread never leaks one tenant's tz into the next request. Fully degrade-safe.
    """

    def process_request(self, request):
        self._activate_timezone(request)
        self._maybe_activate_language(request)
        return None

    def process_response(self, request, response):
        self._deactivate_timezone()
        return response

    def process_exception(self, request, exception):
        self._deactivate_timezone()
        return None

    @staticmethod
    def _deactivate_timezone():
        try:
            from django.utils import timezone

            timezone.deactivate()
        except Exception:  # noqa: BLE001 - tz reset must never break the response
            pass

    def _activate_timezone(self, request):
        school = getattr(request, "school", None)
        tzname = (getattr(school, "timezone", "") or "").strip() if school else ""
        if not tzname:
            return
        try:
            import zoneinfo

            from django.utils import timezone

            timezone.activate(zoneinfo.ZoneInfo(tzname))
        except Exception as exc:  # noqa: BLE001 - bad tz string must not break the request
            logger.debug(
                "TenantLocaleMiddleware tz activate skipped tz=%s err=%s", tzname, exc
            )

    def _maybe_activate_language(self, request):
        school = getattr(request, "school", None)
        lang = (getattr(school, "default_language", "") or "").strip() if school else ""
        if not lang:
            return
        try:
            from django.conf import settings
            from django.utils import translation

            # Respect an explicit language cookie — the strongest no-auth signal.
            cookie_name = getattr(settings, "LANGUAGE_COOKIE_NAME", "django_language")
            if request.COOKIES.get(cookie_name):
                return
            # Only fill when the currently-resolved language is still the bare platform
            # default (i.e. no cookie / matched Accept-Language / user preference won).
            current = (translation.get_language() or "").split("-")[0]
            default = (getattr(settings, "LANGUAGE_CODE", "en") or "en").split("-")[0]
            if current and current != default:
                return
            supported = {code for code, _ in getattr(settings, "LANGUAGES", [])}
            norm = lang.replace("_", "-")
            candidate = norm if norm in supported else norm.split("-")[0]
            if candidate in supported:
                translation.activate(candidate)
                request.LANGUAGE_CODE = translation.get_language()
        except Exception as exc:  # noqa: BLE001 - locale activation must not break the request
            logger.debug(
                "TenantLocaleMiddleware language activate skipped lang=%s err=%s", lang, exc
            )
