"""
Pure helpers for marketing-related Django settings (no DB, no request).

Keeps demo-tenant URL derivation testable without reloading settings.
"""

from __future__ import annotations


def derive_marketing_demo_tenant_url(
    explicit_url: str,
    tenant_example_slug: str | None,
    multi_tenant_base: str,
) -> str:
    """
    Return MARKETING_DEMO_TENANT_URL: explicit env wins; else https://{slug}.{base}/ when both set.
    """
    explicit = (explicit_url or "").strip()
    if explicit:
        return explicit
    slug = (tenant_example_slug or "").strip() if tenant_example_slug else ""
    base = (multi_tenant_base or "").strip().lower()
    if slug and base:
        return f"https://{slug}.{base}/"
    return ""
