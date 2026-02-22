"""
Multi-tenant middleware: resolve request host (subdomain or custom domain) to School,
set request.school and session school_id, and set PostgreSQL app.current_school_id for RLS.
"""
import os
import logging
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Paths that do not require a resolved school (Super Admin, static, health, etc.)
# /admin/ is NOT skipped: on base domain we resolve no tenant → Main (Public) Admin; on tenant subdomain we redirect to Backend
SUPER_PREFIXES = ("/super/",)
STATIC_PREFIXES = ("/static/", "/media/", "/favicon.ico", "/api/schema", "/offline/")
HEALTH_PREFIXES = ("/health", "/ready", "/api/health")

# Option A path-based tenancy: tenant pages live under /t/<school_slug>/ so main URL serves only main admin.
TENANT_PATH_PREFIX = "/t/"
# Root-level path prefixes that are tenant-only; on base domain we redirect these to /t/<slug><path>
ROOT_TENANT_PATH_PREFIXES = (
    "/authentication/",
    "/portal/",
    "/evals/",
    "/academics/",
    "/reports/",
    "/analytics/",
    "/finance/",
    "/payroll/",
    "/compliance/",
    "/communication/",
    "/requests/",
    "/kb/",
    "/siteconfig/",
    "/api-center/",
    "/api/",
    "/emis/",
)


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
    """Return path with /t/<slug> stripped. E.g. /t/gilead/authentication/login/ -> /authentication/login/"""
    prefix = f"/t/{slug}/"
    prefix_alt = f"/t/{slug}"
    if path.startswith(prefix):
        return path[len(prefix) :] or "/"
    if path == prefix_alt or path.startswith(prefix_alt + "/"):
        return path[len(prefix_alt) :] or "/"
    return path


def _is_root_tenant_path(path: str) -> bool:
    """True if path is a tenant-scoped path at root (so we redirect to /t/<slug><path> on base domain)."""
    path = (path or "").strip()
    for prefix in ROOT_TENANT_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix.rstrip("/") + "/") or path.startswith(prefix):
            return True
    return False


def _get_single_tenant_school():
    """Return the single School when SINGLE_TENANT mode is on (one school in DB)."""
    from apps.schools.models import School
    return School.objects.filter(is_active=True).first()


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
    base = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip().lower()
    if base:
        return base
    # Render sets this to the service hostname (e.g. school-management-system-2kzk.onrender.com)
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
    if render_host:
        return render_host
    return ""


def _is_base_domain(host: str, base_domain: str) -> bool:
    """
    True if this host is the primary/base domain (no tenant subdomain).
    On base domain we never assign a tenant: Main (Public) Admin only; tenants use subdomain/custom domain.
    """
    if base_domain:
        return host == base_domain
    return host in ("localhost", "127.0.0.1")


def _resolve_school_from_request(request) -> "School | None":
    from apps.schools.models import School

    host = request.get_host().split(":")[0].lower()
    base_domain = _get_base_domain()

    # 1. Custom domain (Phase 4)
    school = School.objects.filter(
        custom_domain__iexact=host,
        custom_domain_verified=True,
        is_active=True,
    ).first()
    if school:
        return school

    # 2. Subdomain
    subdomain = _extract_subdomain(host, base_domain or None)
    if subdomain:
        school = School.objects.filter(
            subdomain__iexact=subdomain,
            is_active=True,
        ).first()
        if school:
            return school
        # Also match by slug
        school = School.objects.filter(
            slug__iexact=subdomain,
            is_active=True,
        ).first()
        if school:
            return school

    # Base domain: no tenant from host (Main Admin at /admin/, /super/). Single-tenant is applied in process_request for non-admin paths so the main URL can serve Backend when only one hostname exists (e.g. Render).
    if _is_base_domain(host, base_domain):
        return None

    # 3. Single-tenant fallback when NOT on base domain
    if os.getenv("SINGLE_TENANT", "").lower() in ("1", "true", "yes"):
        return _get_single_tenant_school()
    single = _get_single_tenant_school()
    if single and School.objects.filter(is_active=True).count() == 1:
        return single

    return None


class TenantMiddleware(MiddlewareMixin):
    """
    Resolve the current school from the request host (subdomain or custom domain).
    Sets request.school, request.session['school_id'], and PostgreSQL app.current_school_id.
    """

    def process_request(self, request):
        path = request.path or ""

        # Skip paths that don't need a school (except /admin/: we resolve tenant so we can redirect tenant /admin/ to Backend)
        for prefix in SUPER_PREFIXES + STATIC_PREFIXES + HEALTH_PREFIXES:
            if path.startswith(prefix):
                request.school = None
                return None

        host = (request.get_host() or "").split(":")[0].lower()
        base_domain = _get_base_domain()
        from apps.schools.models import School

        # Option A path-based tenancy: /t/<slug>/... → resolve school from slug, rewrite path, set tenant_path_prefix
        if _path_starts_with_tenant_prefix(path):
            slug = _extract_slug_from_tenant_path(path)
            if slug:
                school = School.objects.filter(slug__iexact=slug, is_active=True).first()
                if not school:
                    school = School.objects.filter(subdomain__iexact=slug, is_active=True).first()
                if school:
                    request.school = school
                    request.tenant_path_prefix = f"/t/{slug}/"
                    inner = _strip_tenant_path_prefix(path, slug)
                    request.path = inner
                    request.path_info = inner
                    request.META["PATH_INFO"] = inner
                    request.session["school_id"] = str(school.id)
                    try:
                        from django.utils import timezone as tz
                        from apps.siteconfig.tenant_config import get_tenant_locale
                        locale = get_tenant_locale(school=school)
                        tz.activate(locale.get("timezone") or locale.get("default_timezone") or "UTC")
                    except Exception as e:
                        logger.debug("Could not activate school timezone: %s", e)
                    try:
                        from django.db import connection
                        if connection.vendor == "postgresql":
                            with connection.cursor() as cursor:
                                cursor.execute("SET LOCAL app.current_school_id = %s", [str(school.id)])
                    except Exception as e:
                        logger.debug("Could not set app.current_school_id: %s", e)
                    return None

        # On base domain: do not serve tenant content at root — redirect tenant paths to /t/<slug><path>
        if _is_base_domain(host, base_domain) and _is_root_tenant_path(path):
            single = _get_single_tenant_school()
            if single and School.objects.filter(is_active=True).count() == 1:
                new_path = f"/t/{single.slug}{path}" if path.startswith("/") else f"/t/{single.slug}/{path}"
                return HttpResponseRedirect(new_path)

        # Resolve school from host (subdomain/custom domain) or from session when not on base domain
        try:
            school = _resolve_school_from_request(request)
            if school is None and not _is_base_domain(host, base_domain) and request.session.get("school_id"):
                school = School.objects.filter(
                    id=request.session["school_id"],
                    is_active=True,
                ).first()
        except Exception as e:
            logger.warning("Tenant resolution failed: %s", e, exc_info=True)
            school = None

        # Base domain, non-tenant paths: only /admin/ and /super/ get no tenant; do NOT assign single-tenant at root (Option A: tenant only under /t/<slug>/)
        request.school = school
        # Tenant backend admin dashboard: on tenant subdomain /admin/ → redirect to tenant Backend URL
        if school and path.startswith("/admin/"):
            try:
                from apps.schools.tenant_url import build_tenant_backend_url
                return HttpResponseRedirect(build_tenant_backend_url(request, school, path="/authentication/backend/"))
            except Exception:
                pass
        if school:
            request.tenant_path_prefix = getattr(request, "tenant_path_prefix", "")  # keep empty when tenant from host
            request.session["school_id"] = str(school.id)
            # Phase A: RLS/timezone — use merged tenant locale (useLocalSettings)
            try:
                from django.utils import timezone as tz
                from apps.siteconfig.tenant_config import get_tenant_locale
                locale = get_tenant_locale(school=school)
                tz.activate(locale.get("timezone") or locale.get("default_timezone") or "UTC")
            except Exception as e:
                logger.debug("Could not activate school timezone: %s", e)
            # Set PostgreSQL session variable for RLS (no-op on SQLite/MySQL)
            try:
                from django.db import connection
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SET LOCAL app.current_school_id = %s",
                            [str(school.id)],
                        )
            except Exception as e:
                logger.debug("Could not set app.current_school_id: %s", e)
        else:
            request.session.pop("school_id", None)

        return None


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


class TenantFreezeMiddleware(MiddlewareMixin):
    """
    Section 8.6: When request.school is set and school.is_frozen is True, redirect to
    /account-frozen/ except for exempt paths. Staff/superuser can bypass to access billing/super.
    Must run after TenantMiddleware and AuthenticationMiddleware.
    """

    def process_request(self, request):
        path = (request.path or "").strip()
        for prefix in FROZEN_EXEMPT_PREFIXES:
            if path.startswith(prefix) or path == prefix.rstrip("/"):
                return None
        # Allow staff/superuser to bypass freeze (e.g. to access billing or super admin)
        if getattr(request, "user", None) and request.user.is_authenticated:
            if getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False):
                return None
        school = getattr(request, "school", None)
        if not school or not getattr(school, "is_frozen", False):
            return None
        from django.shortcuts import redirect
        return redirect("account_frozen")


class SentryTenantTagMiddleware(MiddlewareMixin):
    """Phase H optional: tag Sentry events with school_id when request.school is set."""
    def process_request(self, request):
        school = getattr(request, "school", None)
        if school:
            try:
                import sentry_sdk
                sentry_sdk.set_tag("school_id", str(school.id))
                sentry_sdk.set_tag("school_slug", getattr(school, "slug", "") or "")
            except Exception:
                pass
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
            cache.set(cache_key, True, timeout=3600)
            from apps.schools.models import School
            School.objects.filter(pk=school.id).update(last_activity=timezone.now())
        except Exception:
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
        # Global toggle: when Super Admin UI is disabled, block /super/ (except parent-tenant if allowed).
        try:
            from apps.siteconfig.models import SiteSettings
            site = SiteSettings.get_solo()
            flags = getattr(site, "backend_feature_flags", None) or {}
            if not flags.get("enable_super_admin_ui", True):
                if not request.path.startswith("/super/parent-tenant"):
                    from django.http import HttpResponseForbidden
                    return HttpResponseForbidden("Super Admin is disabled.")
        except Exception:
            pass
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if getattr(request.user, "is_superuser", False):
            return None
        role = (getattr(request.user, "role", "") or "").upper()
        if role == "SUPERADMIN":
            return None
        # Parent-tenant dashboard: allow users whose school has child_schools (Phase 4).
        if request.path.startswith("/super/parent-tenant"):
            from apps.schools.models import SchoolMembership
            school_id = request.session.get("school_id")
            if school_id:
                from apps.schools.models import School
                parent = School.objects.filter(id=school_id, is_active=True).first()
                if parent and parent.child_schools.exists():
                    return None
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Super Admin access required.")


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


def _feature_gate_403(request, feature_code: str):
    """Return 403 response (JSON for API, HTML for browser)."""
    from django.http import HttpResponseForbidden, JsonResponse
    if request.path.startswith("/api/") or (request.headers.get("Accept") or "").find("application/json") >= 0:
        return JsonResponse(
            {"error": "feature_not_available", "feature": feature_code, "detail": "This feature is not enabled for your plan."},
            status=403,
        )
    return HttpResponseForbidden(
        f"<h1>403 Forbidden</h1><p>This feature ({feature_code}) is not enabled for your plan. Contact your administrator or upgrade.</p>"
    )


class FeatureGatekeeperMiddleware(MiddlewareMixin):
    """
    Phase D: Enforce feature access by path. If request.school is set and the path
    matches FEATURE_GATE_PATH_MAP, require is_feature_enabled(school, code); else return 403.
    Must run after TenantMiddleware so request.school is set.
    """

    def process_request(self, request):
        path = (request.path or "").strip()
        school = getattr(request, "school", None)
        if not school:
            return None
        for prefix, code in FEATURE_GATE_PATH_MAP.items():
            if not code:
                continue
            if path == prefix or path.startswith(prefix.rstrip("/") + "/") or path == prefix.rstrip("/"):
                from apps.schools.models import is_feature_enabled
                if not is_feature_enabled(school, code):
                    return _feature_gate_403(request, code)
                break
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
            request.admin_theme_choice = getattr(request, "admin_theme_choice", "UNFOLD")
        return None


class UsageLimitMiddleware(MiddlewareMixin):
    """
    Phase D (optional): Enforce Plan max_students / max_staff. Enable with
    ENABLE_USAGE_LIMIT_MIDDLEWARE=True. When over limit, returns 403 with message.
    """

    def process_request(self, request):
        import os
        if os.getenv("DISABLE_USAGE_LIMIT_MIDDLEWARE", "").strip().lower() in ("1", "true", "yes"):
            return None
        school = getattr(request, "school", None)
        if not school:
            return None
        # Phase E: Skip usage limits for waived schools (full access)
        if getattr(school, "billing_type", None) in ("COMPLIMENTARY", "MANUAL_OVERRIDE"):
            return None
        plan = getattr(school, "plan", None)
        if not plan:
            return None
        from django.http import JsonResponse, HttpResponseForbidden
        if getattr(plan, "max_students", None) is not None:
            from apps.people.models import StudentProfile
            count = StudentProfile.objects.filter(school=school).count()
            if count >= plan.max_students:
                if request.path.startswith("/api/") or (request.headers.get("Accept") or "").find("application/json") >= 0:
                    return JsonResponse(
                        {"error": "usage_limit", "limit": "max_students", "detail": "Student limit reached for your plan."},
                        status=403,
                    )
                return HttpResponseForbidden("<h1>403</h1><p>Student limit reached for your plan. Please upgrade.</p>")
        if getattr(plan, "max_staff", None) is not None:
            from apps.people.models import TeacherProfile
            count = TeacherProfile.objects.filter(school=school).count()
            if count >= plan.max_staff:
                if request.path.startswith("/api/") or (request.headers.get("Accept") or "").find("application/json") >= 0:
                    return JsonResponse(
                        {"error": "usage_limit", "limit": "max_staff", "detail": "Staff limit reached for your plan."},
                        status=403,
                    )
                return HttpResponseForbidden("<h1>403</h1><p>Staff limit reached for your plan. Please upgrade.</p>")
        return None
