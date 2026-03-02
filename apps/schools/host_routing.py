"""
Shared host-routing helpers for public vs tenant access points.
"""
from __future__ import annotations

import ipaddress
import os


LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "testserver",
    "admin.localhost",
    "manager.localhost",
    "api.localhost",
    "docs.localhost",
}
RESERVED_PUBLIC_SUBDOMAINS = {"www", "admin", "verify", "support", "api", "docs", "manager"}


def normalize_host(host: str) -> str:
    value = (host or "").strip().lower()
    if ":" in value:
        value = value.split(":", 1)[0].strip().lower()
    return value.rstrip(".")


def get_canonical_base_domain() -> str:
    base = (os.getenv("MULTI_TENANT_BASE_DOMAIN") or "").strip().lower()
    if base:
        return base
    # Canonical production domain is fixed for this platform.
    # Do not fall back to provider hostnames (e.g. *.onrender.com),
    # otherwise public-host detection can misclassify the real apex domain.
    return "runmycampus.com"


def get_legacy_base_domains() -> set[str]:
    """
    Comma-separated legacy domains kept alive during cutover.
    Default keeps the previous production domain.
    """
    raw = (os.getenv("MULTI_TENANT_LEGACY_BASE_DOMAINS") or "").strip().lower()
    values = {item.strip() for item in raw.split(",") if item.strip()}
    canonical = get_canonical_base_domain()
    if canonical in values:
        values.remove(canonical)
    return values


def public_hosts_for_domain(base_domain: str) -> set[str]:
    if not base_domain:
        return set()
    hosts = {base_domain}
    for sub in RESERVED_PUBLIC_SUBDOMAINS:
        hosts.add(f"{sub}.{base_domain}")
    return hosts


def all_public_hosts() -> set[str]:
    hosts = set(LOCAL_HOSTS)
    canonical = get_canonical_base_domain()
    if canonical:
        hosts |= public_hosts_for_domain(canonical)
    for legacy in get_legacy_base_domains():
        hosts |= public_hosts_for_domain(legacy)
    return hosts


def is_public_host(host: str) -> bool:
    normalized = normalize_host(host)
    if not normalized:
        return True
    if normalized.endswith(".onrender.com"):
        return True
    try:
        ipaddress.ip_address(normalized)
        return True
    except ValueError:
        pass
    return normalized in all_public_hosts()


def public_host_kind(host: str) -> str | None:
    normalized = normalize_host(host)
    if normalized in LOCAL_HOSTS:
        return "local"
    if normalized.endswith(".onrender.com"):
        return "base"
    try:
        ipaddress.ip_address(normalized)
        return "local"
    except ValueError:
        pass
    render_host = (os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip().lower()
    if render_host and normalized == render_host:
        return "base"

    for base in [get_canonical_base_domain(), *sorted(get_legacy_base_domains())]:
        if not base:
            continue
        if normalized == base or normalized == f"www.{base}" or normalized == f"admin.{base}":
            return "base"
        if normalized == f"verify.{base}":
            return "verify"
        if normalized == f"support.{base}":
            return "support"
        if normalized == f"manager.{base}":
            return "manager"
        if normalized == f"api.{base}":
            return "api"
        if normalized == f"docs.{base}":
            return "docs"
    return None


def map_legacy_host_to_canonical(host: str) -> str | None:
    """
    Return canonical replacement host when `host` belongs to a legacy base domain.
    """
    canonical = get_canonical_base_domain()
    if not canonical:
        return None
    normalized = normalize_host(host)
    if not normalized:
        return None
    for legacy in get_legacy_base_domains():
        if normalized == legacy:
            return canonical
        suffix = f".{legacy}"
        if normalized.endswith(suffix):
            prefix = normalized[: -len(suffix)]
            return f"{prefix}.{canonical}" if prefix else canonical
    return None


def is_local_dev_host(host: str) -> bool:
    normalized = normalize_host(host)
    return normalized in LOCAL_HOSTS or normalized.endswith(".localhost")


def allow_path_based_tenant_fallback(host: str, debug: bool = False) -> bool:
    """
    `/t/<slug>/` rendering is disabled by default for strict subdomain tenancy.
    Allow only when explicitly enabled in local/dev.
    """
    if not (debug or is_local_dev_host(host)):
        return False
    return os.getenv("ALLOW_PATH_TENANT_FALLBACK", "").strip().lower() in {"1", "true", "yes"}
