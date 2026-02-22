"""
Tenant URL helpers: base-domain detection and building tenant (subdomain/custom domain or path-based /t/<slug>/) URLs.
Used so Main (Public) Admin stays on the primary domain and tenant Backend is only on subdomain/custom domain or /t/<slug>/.
"""
import os


def get_single_tenant_slug() -> str | None:
    """When exactly one active school exists, return its slug for path-based tenant URLs. Else None."""
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
    base = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip().lower()
    if base:
        return base
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
    if render_host:
        return render_host
    return ""


def is_base_domain(request) -> bool:
    """
    Return True if the request host is the primary/base domain (no tenant subdomain).
    On the base domain we do not assign a tenant: Main Admin only.
    """
    host = (request.get_host() or "").split(":")[0].lower()
    base_domain = get_base_domain()
    if base_domain:
        return host == base_domain
    return host in ("localhost", "127.0.0.1")


def get_tenant_prefix(request) -> str:
    """
    Return the path prefix for tenant URLs when using path-based tenancy (Option A).
    E.g. '/t/gilead/'. Empty when tenant is identified by host (subdomain/custom domain).
    Use when building links or redirects so tenant pages stay under /t/<slug>/.
    """
    return getattr(request, "tenant_path_prefix", "") or ""


def build_tenant_backend_url(request, school, path: str = "/authentication/backend/") -> str:
    """
    Build the full URL for a tenant's Backend (subdomain, custom domain, or path-based /t/<slug>/).
    Use after login when user is on the base domain but has a school membership.
    On base domain (Option A) with no custom domain, use path-based /t/<slug><path>.
    """
    prefix = get_tenant_prefix(request)
    if prefix:
        path = path if path.startswith("/") else f"/{path}"
        return request.build_absolute_uri(prefix.rstrip("/") + path)

    # Option A: on base domain use path-based tenant URL so tenant is never served from root
    if is_base_domain(request):
        slug = (getattr(school, "slug", None) or getattr(school, "subdomain", None) or "").strip().lower()
        if slug:
            path = path if path.startswith("/") else f"/{path}"
            return request.build_absolute_uri(f"/t/{slug}{path}")

    scheme = "https" if getattr(request, "is_secure", lambda: False)() else "http"
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
