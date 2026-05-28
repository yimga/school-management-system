"""Thread-local regional DB alias (batch 1535) — env-gated, no runtime DATABASES mutation."""

from __future__ import annotations

import threading
from typing import Any

from django.conf import settings

_local = threading.local()


def set_request_db_alias(alias: str | None) -> None:
    _local.db_alias = (alias or "").strip() or None


def get_request_db_alias() -> str | None:
    return getattr(_local, "db_alias", None)


def clear_request_db_alias() -> None:
    if hasattr(_local, "db_alias"):
        del _local.db_alias


def resolve_school_db_alias(school: Any) -> str | None:
    """
    Operational shard alias for ``school`` when multi-region is enabled.

    Returns a key present in ``settings.DATABASES`` or ``None`` (default router).
    """
    if not getattr(settings, "ENABLE_MULTI_REGION", False):
        return None
    if school is None:
        return None
    databases = getattr(settings, "DATABASES", {})
    dedicated = (getattr(school, "dedicated_db_alias", None) or "").strip()
    if dedicated and dedicated in databases:
        return dedicated
    region = (getattr(school, "regional_cluster", None) or "").strip()
    if region and region in databases:
        return region
    data_region = (getattr(school, "data_region", None) or "").strip()
    if data_region and data_region in databases:
        return data_region
    return None


def effective_db_alias(*, school: Any = None, tenant: Any = None) -> str | None:
    """Prefer thread-local override, then school / tenant resolution."""
    override = get_request_db_alias()
    if override:
        return override
    if school is not None:
        return resolve_school_db_alias(school)
    if tenant is not None:
        school = getattr(tenant, "school", None)
        if school is not None:
            return resolve_school_db_alias(school)
        alias = getattr(tenant, "db_alias", None) or ""
        alias = alias.strip()
        if alias and alias in getattr(settings, "DATABASES", {}):
            return alias
    return None


__all__ = [
    "clear_request_db_alias",
    "effective_db_alias",
    "get_request_db_alias",
    "resolve_school_db_alias",
    "set_request_db_alias",
]
