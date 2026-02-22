"""
Tenant URL helpers: base-domain detection and building tenant (subdomain/custom domain) URLs.
Used so Main (Public) Admin stays on the primary domain and tenant Backend is only on subdomain/custom domain.
"""
import os


def is_base_domain(request) -> bool:
    """
    Return True if the request host is the primary/base domain (no tenant subdomain).
    On the base domain we do not assign a tenant: Main Admin only.
    """
    host = (request.get_host() or "").split(":")[0].lower()
    base_domain = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip().lower()
    if base_domain:
        return host == base_domain
    return host in ("localhost", "127.0.0.1")


def build_tenant_backend_url(request, school, path: str = "/authentication/backend/") -> str:
    """
    Build the full URL for a tenant's Backend (subdomain or custom domain).
    Use after login when user is on the base domain but has a school membership.
    """
    scheme = "https" if getattr(request, "is_secure", lambda: False)() else "http"
    host = (request.get_host() or "").strip()
    host_no_port = host.split(":")[0].lower()
    port = host.split(":")[-1] if ":" in host else None
    base_domain = os.getenv("MULTI_TENANT_BASE_DOMAIN", "").strip().lower() or host_no_port

    if getattr(school, "custom_domain", None) and getattr(school, "custom_domain_verified", False):
        tenant_host = school.custom_domain.strip().lower()
    else:
        sub = (getattr(school, "subdomain", None) or getattr(school, "slug", None) or "").strip().lower()
        tenant_host = f"{sub}.{base_domain}" if sub else base_domain

    if port and port not in ("80", "443"):
        tenant_host = f"{tenant_host}:{port}"
    path = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{tenant_host}{path}"
