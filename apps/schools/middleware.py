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
SUPER_PREFIXES = ("/super/",)
STATIC_PREFIXES = ("/static/", "/media/", "/favicon.ico", "/api/schema", "/offline/")
HEALTH_PREFIXES = ("/health", "/ready", "/api/health")


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


def _resolve_school_from_request(request) -> "School | None":
    from apps.schools.models import School

    host = request.get_host().split(":")[0].lower()
    base_domain = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip().lower()

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

    # 3. Single-tenant: one school in DB or SINGLE_TENANT=true
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

        # Skip paths that don't need a school
        for prefix in SUPER_PREFIXES + STATIC_PREFIXES + HEALTH_PREFIXES:
            if path.startswith(prefix):
                request.school = None
                return None

        # Resolve school from host (subdomain/custom domain) or from session (e.g. main domain after login)
        try:
            school = _resolve_school_from_request(request)
            if school is None and request.session.get("school_id"):
                from apps.schools.models import School
                school = School.objects.filter(
                    id=request.session["school_id"],
                    is_active=True,
                ).first()
        except Exception as e:
            logger.warning("Tenant resolution failed: %s", e, exc_info=True)
            school = None

        request.school = school
        if school:
            request.session["school_id"] = str(school.id)
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
