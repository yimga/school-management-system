"""Env-driven defaults for the platform founding / bootstrap tenant.

Historical migrations ``0012``/``0013`` seeded a founding-school row; those files
are frozen. New bootstrap paths (Render release command, local dev) MUST route
through ``DEFAULT_TENANT_*`` env vars instead of hardcoding that slug.

When env is unset, defaults to the neutral ``demo-school`` sandbox — not the
migration-era slug — so fresh operator installs never inherit founding-school
branding unless they opt in via env.
"""

from __future__ import annotations

import os
import re

# Platform-neutral bootstrap default (matches ensure_developer_sandbox_tenant).
_FALLBACK_SLUG = "demo-school"
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def resolve_founding_tenant_slug(*, override: str | None = None) -> str:
    """Return the tenant slug for bootstrap commands."""
    raw = (override or os.environ.get("DEFAULT_TENANT_SLUG") or "").strip().lower()
    if not raw:
        return _FALLBACK_SLUG
    if not _SLUG_RE.match(raw):
        raise ValueError(f"invalid tenant slug {raw!r}")
    return raw


def resolve_founding_tenant_name(*, slug: str | None = None, override: str | None = None) -> str:
    """Human-readable tenant name for bootstrap commands."""
    name = (override or os.environ.get("DEFAULT_TENANT_NAME") or "").strip()
    if name:
        return name[:255]
    slug_val = slug or resolve_founding_tenant_slug()
    return slug_val.replace("-", " ").replace("_", " ").title()


def resolve_founding_tenant_subdomain(*, slug: str | None = None, override: str | None = None) -> str:
    """Subdomain/host label for bootstrap commands."""
    sub = (override or os.environ.get("DEFAULT_TENANT_SUBDOMAIN") or "").strip().lower()
    if sub:
        if not _SLUG_RE.match(sub):
            raise ValueError(f"invalid tenant subdomain {sub!r}")
        return sub[:63]
    return slug or resolve_founding_tenant_slug()


def founding_tenant_env_explicit() -> bool:
    """True when operator set any DEFAULT_TENANT_* env var (prod-safe signal)."""
    return any(
        (os.environ.get(key) or "").strip()
        for key in (
            "DEFAULT_TENANT_SLUG",
            "DEFAULT_TENANT_NAME",
            "DEFAULT_TENANT_SUBDOMAIN",
        )
    )
