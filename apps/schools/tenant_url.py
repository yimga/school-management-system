"""
Tenant URL helpers: base-domain detection and building tenant URLs.
"""
from django.conf import settings
from django.urls import reverse
from apps.schools.host_routing import (
    get_canonical_base_domain,
    is_local_dev_host,
    public_host_kind,
)


def get_single_tenant_slug() -> str | None:
    """When exactly one active school exists, return its slug (legacy helper)."""
    try:
        from apps.schools.models import School
        schools = list(School.objects.filter(is_active=True).values_list("slug", flat=True)[:2])
        return schools[0] if len(schools) == 1 else None
    except Exception:
        return None


def get_base_domain() -> str:
    """
    Canonical base domain (same logic as middleware). Use MULTI_TENANT_BASE_DOMAIN if set;
    on Render when unset, use RENDER_EXTERNAL_HOSTNAME so the primary URL is base domain.
    """
    return get_canonical_base_domain()


def is_base_domain(request) -> bool:
    """
    Return True if the request host is the primary/base domain (no tenant subdomain).
    On the base domain we do not assign a tenant: Main Admin only.
    """
    host = (request.get_host() or "").split(":")[0].lower()
    return public_host_kind(host) in {"base", "local"}


def get_tenant_prefix(request) -> str:
    """
    Return request-scoped tenant path prefix (legacy compatibility only).
    Empty when tenant is identified by host (subdomain/custom domain).
    """
    return getattr(request, "tenant_path_prefix", "") or ""


def build_tenant_backend_url(request, school, path: str = "/authentication/backend/") -> str:
    """
    Build the full URL for a tenant's Backend (subdomain or verified custom domain).
    Use after login when user is on the base domain but has a school membership.
    """
    prefix = get_tenant_prefix(request)
    if prefix:
        path = path if path.startswith("/") else f"/{path}"
        return request.build_absolute_uri(prefix.rstrip("/") + path)

    scheme = "https" if getattr(request, "is_secure", lambda: False)() or not getattr(settings, "DEBUG", False) else "http"
    host = (request.get_host() or "").strip()
    host_no_port = host.split(":")[0].lower()
    port = host.split(":")[-1] if ":" in host else None
    base_domain = get_base_domain() or host_no_port

    if getattr(school, "custom_domain", None) and getattr(school, "custom_domain_verified", False):
        tenant_host = school.custom_domain.strip().lower()
    else:
        sub = (getattr(school, "subdomain", None) or getattr(school, "slug", None) or "").strip().lower()
        tenant_host = f"{sub}.{base_domain}" if sub else base_domain

    if port and port not in ("80", "443"):
        tenant_host = f"{tenant_host}:{port}"
    path = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{tenant_host}{path}"


def build_manager_absolute_url(request, path: str = "/super/") -> str:
    scheme = "https" if getattr(request, "is_secure", lambda: False)() or not getattr(settings, "DEBUG", False) else "http"
    host = (request.get_host() or "").strip()
    host_no_port = host.split(":")[0].lower()
    port = host.split(":")[-1] if ":" in host else None
    if is_local_dev_host(host_no_port) or public_host_kind(host_no_port) == "local":
        manager_host = "manager.localhost"
    else:
        manager_host = f"manager.{get_base_domain()}"
    if port and port not in ("80", "443"):
        manager_host = f"{manager_host}:{port}"
    path = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{manager_host}{path}"


def build_public_absolute_url(request, path: str = "/") -> str:
    scheme = "https" if getattr(request, "is_secure", lambda: False)() or not getattr(settings, "DEBUG", False) else "http"
    host = (request.get_host() or "").strip()
    host_no_port = host.split(":")[0].lower()
    port = host.split(":")[-1] if ":" in host else None
    if is_local_dev_host(host_no_port) or public_host_kind(host_no_port) == "local":
        public_host = "localhost"
    else:
        public_host = get_base_domain()
    if port and port not in ("80", "443"):
        public_host = f"{public_host}:{port}"
    path = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{public_host}{path}"


def tenant_absolute_url(request, viewname, *args, school=None, path=None, **kwargs):
    """
    Build a tenant-aware absolute URL for the given view.
    When request.school (or passed school) is set, produces a full URL on the correct
    subdomain/custom domain so emails and redirects stay tenant-scoped.
    """
    path = reverse(viewname, args=args, kwargs=kwargs)
    s = school or getattr(request, "school", None)
    if s:
        return build_tenant_backend_url(request, s, path=path)
    return request.build_absolute_uri(path)
